"""Request-level tests for the security review copy."""
import io
import importlib
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from PIL import Image

os.environ["CAMPUS_SECRET"] = "isolated-test-secret-" * 3
os.environ["CAMPUS_SECURITY_DEMO"] = "1"
from app import db, passwords
from app.main import app

ORIGIN = {"origin": "http://testserver"}

@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.sqlite3"))
    db.setup()
    import app.main as module
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(module, "UPLOADS", str(upload_dir))
    users = [db.create_user(f"{10000 + index}@novasbe.pt", name, "finance",
             passwords.hash_password("TestPassword1!")) for index, name in enumerate(("alice", "bob", "clara"))]
    conn = db.connect()
    with conn:
        conn.execute("UPDATE users SET verified=1")
    conn.close()
    clients = [TestClient(app) for _ in users]
    for client, member in zip(clients, users):
        response = client.post("/dev", data={"user_id":member}, headers=ORIGIN, follow_redirects=False)
        assert response.status_code == 303
    return users, clients

def test_verified_nova_gate(world):
    users, clients = world
    conn = db.connect()
    with conn:
        conn.execute("UPDATE users SET verified=0 WHERE id=?", (users[0],))
        conn.execute("UPDATE users SET email='outsider@gmail.com' WHERE id=?", (users[1],))
    conn.close()
    for client in clients[:2]:
        assert client.get("/housing", follow_redirects=False).status_code == 303

def test_forged_origin_and_missing_origin(world):
    _, clients = world
    for headers in ({}, {"origin":"https://attacker.example"}):
        assert clients[0].post("/logout", headers=headers).status_code == 403
    assert clients[0].post("/logout", headers=ORIGIN, follow_redirects=False).status_code == 303

def test_chat_privacy_and_owner_actions(world):
    users, clients = world
    a,b,c = users
    listing = db.create_listing(a,"item","Room for testing",price=10)
    thread = db.open_conversation(listing,b)
    assert clients[1].post(f"/chat/{thread}", data={"body":"PRIVATE_MARKER"}, headers=ORIGIN,
                           follow_redirects=False).status_code == 303
    assert "PRIVATE_MARKER" in clients[0].get(f"/chat/{thread}").text
    assert "PRIVATE_MARKER" not in clients[2].get(f"/chat/{thread}").text
    before=len(db.messages_of(thread))
    clients[2].post(f"/chat/{thread}", data={"body":"intrusion"}, headers=ORIGIN)
    assert len(db.messages_of(thread)) == before
    assert db.send_message(thread,c,"direct intrusion") is None
    clients[1].post(f"/listing/{listing}/close",headers=ORIGIN)
    assert db.get_listing(listing)["status"]=="open"
    clients[0].post(f"/listing/{listing}/close",headers=ORIGIN)
    assert db.get_listing(listing)["status"]=="closed"
    clients[1].post(f"/listing/{listing}/reopen",headers=ORIGIN)
    assert db.get_listing(listing)["status"]=="closed"

@pytest.mark.parametrize("price", ["not a number","-1","NaN","Infinity","100001"])
def test_invalid_price_never_creates_listing(world, price):
    users, clients=world
    before=len(db.listings_of_user(users[0]))
    response=clients[0].post("/new", data={"kind":"item","title":"Test","description":"A used desk", "price":price}, headers=ORIGIN)
    assert response.status_code==200
    assert len(db.listings_of_user(users[0]))==before

def test_image_content_and_size(world):
    users, clients=world
    before=len(db.listings_of_user(users[0]))
    for data in (b"not-an-image", b"x"*5_000_001):
        response=clients[0].post("/new",data={"kind":"item","title":"Bad photo","description":"A used desk", "price":"5"},
                               files={"photos":("photo.jpg",data,"image/jpeg")},headers=ORIGIN)
        assert response.status_code==400
        assert len(db.listings_of_user(users[0]))==before
    output=io.BytesIO()
    Image.new("RGB",(20,20)).save(output,"PNG")
    response=clients[0].post("/new",data={"kind":"item","title":"Photo","description":"A used desk", "price":"5"},
                            files={"photos":("photo.png",output.getvalue(),"image/png")},
                            headers=ORIGIN,follow_redirects=False)
    assert response.status_code==303

def test_html_is_escaped(world):
    users, clients=world
    listing=db.create_listing(users[0],"item","<script>alert(1)</script>",price=1)
    page=clients[1].get(f"/listing/{listing}").text
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page

def test_login_rate_limit(world):
    _, clients=world
    for _ in range(20):
        assert clients[0].post("/login",data={"email":"99999@novasbe.pt","password":"incorrect"},
                               headers=ORIGIN).status_code==200
    assert clients[0].post("/login",data={"email":"99999@novasbe.pt"},headers=ORIGIN).status_code==429

def test_single_use_is_atomic(world):
    users,_=world
    code=db.new_code(users[0])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _: db.check_code(users[0],code), range(2)))
    assert results.count("ok")==1

def test_email_code_flow(world):
    users,_=world
    code=db.new_code(users[0])
    assert code != db.get_user(users[0])["code"]
    assert db.check_code(users[0],code,"reset")=="none"
    assert db.check_code(users[0],code)=="ok"
    assert db.check_code(users[0],code)=="none"

def test_no_image_access_signed_out(world):
    response=TestClient(app).get("/static/uploads/example.jpg")
    assert response.status_code==403

def test_security_headers(world):
    response=world[1][0].get("/housing")
    assert response.headers["x-content-type-options"]=="nosniff"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]

def test_production_disables_demo_and_secures_cookie(world):
    import app.main as module
    with patch.object(module,"LOCAL_DEMO",False):
        client=TestClient(app)
        assert client.get("/dev").status_code==404
        assert client.post("/dev",data={"user_id":world[0][0]},headers=ORIGIN).status_code==404

def test_registration_sends_code_and_requires_verification(world, monkeypatch):
    from app import main, mailer, programmes
    deliveries=[]
    monkeypatch.setattr(mailer,"is_set_up",lambda:True)
    monkeypatch.setattr(mailer,"send_code",lambda email,code,why: deliveries.append((email,code)) or True)
    client=TestClient(app)
    fields={"name":"New Student","programme":programmes.MASTER[0][0] if isinstance(programmes.MASTER[0],tuple) else programmes.MASTER[0],
            "email":"12345@novasbe.pt","password":"TestPassword1!","password2":"TestPassword1!"}
    response=client.post("/join",data=fields,headers=ORIGIN,follow_redirects=False)
    assert response.status_code==303, response.text
    assert len(deliveries)==1
    assert deliveries[0][0]=="12345@novasbe.pt"
    assert client.get("/housing",follow_redirects=False).status_code==303
    code=deliveries[0][1]
    assert client.post("/verify",data={f"d{i+1}":n for i,n in enumerate(code)},
                       headers=ORIGIN,follow_redirects=False).status_code==303
    assert client.get("/housing").status_code==200

def test_expiry_five_guesses_and_cancelled_delivery(world):
    user=world[0][0]
    code=db.new_code(user)
    for _ in range(4):
        assert db.check_code(user,"invalid")=="wrong"
    assert db.check_code(user,"invalid")=="locked"
    assert db.check_code(user,code)=="locked"
    conn=db.connect()
    with conn:
        conn.execute("UPDATE users SET code_sent=? WHERE id=?",
                    ((datetime.now(timezone.utc)-timedelta(seconds=61)).isoformat(),user))
    conn.close()
    replacement=db.new_code(user)
    assert db.check_code(user,code)=="wrong"
    db.cancel_code(user,replacement,"join")
    assert db.check_code(user,replacement)=="none"
    conn=db.connect()
    with conn:
        conn.execute("UPDATE users SET code_sent=? WHERE id=?",
                    ((datetime.now(timezone.utc)-timedelta(seconds=61)).isoformat(),user))
    conn.close()
    code=db.new_code(user)
    conn=db.connect()
    with conn:
        conn.execute("UPDATE users SET code_sent=? WHERE id=?",
                    ((datetime.now(timezone.utc)-timedelta(seconds=601)).isoformat(),user))
    conn.close()
    assert db.check_code(user,code)=="expired"

def test_production_cookie_and_dev_route_in_fresh_process(world):
    import subprocess, sys, textwrap
    env=os.environ.copy()
    env["CAMPUS_SECURITY_DEMO"]="0"
    env["CAMPUS_DB"]=db.DB_PATH
    result=subprocess.run([sys.executable,"-c",textwrap.dedent("""
        from fastapi.testclient import TestClient
        from app.main import app
        from app import db
        user=db.all_users()[0]
        client=TestClient(app,base_url="https://testserver")
        assert client.get("/dev").status_code==404
        response=client.post("/login",data={"email":user["email"],"password":"TestPassword1!"},
                             headers={"origin":"https://testserver"},follow_redirects=False)
        assert response.status_code==303
        cookie=response.headers["set-cookie"].lower()
        assert "secure" in cookie and "httponly" in cookie and "samesite=lax" in cookie
        assert client.get("/housing").status_code==200
    """)],env=env,capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr

def test_missing_production_secret_refuses_start(world):
    import subprocess,sys
    env=os.environ.copy()
    env["CAMPUS_SECRET"]=""
    env["CAMPUS_SECURITY_DEMO"]="0"
    result=subprocess.run([sys.executable,"-c","import app.main"],env=env,
                          capture_output=True,text=True,timeout=20)
    assert result.returncode!=0
    assert "Set CAMPUS_SECRET" in result.stderr

@pytest.mark.parametrize("estimate", ["invalid", "-5", "NaN", "Infinity"])
def test_invalid_housing_bills_are_rejected(world, estimate):
    users, clients = world
    before = len(db.listings_of_user(users[0]))
    response = clients[0].post("/new", data={
        "kind":"housing", "title":"Test room", "price":"400", "bills_estimate":estimate,
        "description":"A furnished room", "available_from":"2027-02-01", "place":"carcavelos",
        "address":"Test Street 1", "deposit":"400", "months_min":"1", "minutes_campus":"10", "flatmates":"2",
    }, headers=ORIGIN)
    assert response.status_code == 200
    assert len(db.listings_of_user(users[0])) == before

def test_housing_fields_survive_valid_publication(world):
    users, clients = world
    response = clients[0].post("/new", data={
        "kind":"housing", "title":"New room", "price":"400", "bills_estimate":"35",
        "category":"shared_flat", "flatmates":"2", "available_from":"2027-02-01",
        "description":"A furnished room", "place":"carcavelos", "address":"Test Street 1",
        "deposit":"400", "months_min":"1", "minutes_campus":"10",
    }, headers=ORIGIN, follow_redirects=False)
    assert response.status_code == 303
    row = db.listings_of_user(users[0])[0]
    assert row["flatmates"] == 2
    assert row["bills_estimate"] == 35


def test_shared_ip_does_not_lock_other_accounts(world):
    _, clients = world
    for _ in range(20):
        clients[0].post("/login", data={"email": "99999@novasbe.pt", "password": "wrong"}, headers=ORIGIN)
    assert clients[0].post("/login", data={"email": "99999@novasbe.pt"}, headers=ORIGIN).status_code == 429
    assert clients[0].post("/login", data={"email": "88888@novasbe.pt"}, headers=ORIGIN).status_code == 200
    assert clients[0].post("/login", data={"email": " 99999@NOVASBE.PT "}, headers=ORIGIN).status_code == 429


def test_bad_signup_photo_keeps_form_and_creates_no_account(world):
    from app import programmes
    client = TestClient(app)
    response = client.post("/join", headers=ORIGIN,
        data={"name": "New Student", "email": "12345@novasbe.pt", "programme": programmes.MASTER[0],
              "password": "TestPassword1!", "password2": "TestPassword1!"},
        files={"photo": ("photo.jpg", b"not an image", "image/jpeg")})
    assert response.status_code == 200
    assert "Upload a valid JPEG, PNG or WebP image." in response.text
    assert db.get_user_by_email("12345@novasbe.pt") is None


def test_terminal_codes_only_in_explicit_demo(world, monkeypatch, capsys):
    from app import main, mailer
    users, _ = world
    monkeypatch.setattr(mailer, "is_set_up", lambda: False)
    monkeypatch.setattr(main, "LOCAL_DEMO", False)
    assert "not configured" in main.send_code(db.get_user(users[0]), "join")
    assert "LOCAL DEMO" not in capsys.readouterr().out
    monkeypatch.setattr(main, "LOCAL_DEMO", True)
    assert main.send_code(db.get_user(users[0]), "join") == ""
    assert "LOCAL DEMO ONLY" in capsys.readouterr().out


def test_trusted_proxy_https_origin_and_untrusted_spoof(world):
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
    proxied = ProxyHeadersMiddleware(app, trusted_hosts=["127.0.0.1"])
    headers = {"origin": "https://testserver", "x-forwarded-proto": "https"}
    trusted = TestClient(proxied, client=("127.0.0.1", 50000))
    assert trusted.post("/logout", headers=headers, follow_redirects=False).status_code == 303
    untrusted = TestClient(proxied, client=("203.0.113.10", 50000))
    assert untrusted.post("/logout", headers=headers, follow_redirects=False).status_code == 403


def test_bad_edit_profile_photo_keeps_form(world):
    from app import programmes
    users, clients = world
    before = db.get_user(users[0])["name"]
    response = clients[0].post("/profile/edit", headers=ORIGIN,
        data={"name": "Changed", "programme": programmes.MASTER[0]},
        files={"photo": ("photo.png", b"not an image", "image/png")})
    assert response.status_code == 200
    assert "Upload a valid JPEG, PNG or WebP image." in response.text
    assert db.get_user(users[0])["name"] == before


def test_listing_edit_preserves_owner_and_rejects_invalid_values(world):
    users, clients = world
    listing = db.create_listing(users[0], "item", "Desk", price=10)
    fields = {"edit_id": str(listing), "kind":"item", "title":"Updated desk",
              "description":"A used desk", "price":"12,50"}
    assert clients[1].post("/new", data=fields, headers=ORIGIN).status_code == 200
    assert db.get_listing(listing)["title"] == "Desk"
    assert clients[0].post("/new", data=fields, headers=ORIGIN, follow_redirects=False).status_code == 303
    assert db.get_listing(listing)["title"] == "Updated desk"
    assert db.get_listing(listing)["price"] == 12.5
    fields["price"] = "NaN"
    assert clients[0].post("/new", data=fields, headers=ORIGIN).status_code == 200
    assert db.get_listing(listing)["price"] == 12.5


@pytest.mark.parametrize("value", ["\u00b2", "9" * 5000])
def test_invalid_numeric_fields_do_not_crash(world, value):
    _, clients = world
    response = clients[0].post("/new", headers=ORIGIN, data={
        "kind":"item", "title":"Desk", "description":"A used desk", "quantity":value})
    assert response.status_code == 200
    assert "Enter whole numbers" in response.text
