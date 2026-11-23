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
    # Through the front door, the one a student uses. The development login
    # that used to stand in here is gone, and signing in properly means the
    # tests below also keep the real door honest.
    for client, member in zip(clients, users):
        response = client.post("/login", headers=ORIGIN, follow_redirects=False,
                               data={"email": db.get_user(member)["email"],
                                     "password": "TestPassword1!"})
        assert response.status_code == 303, response.text
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

@pytest.mark.parametrize("price", ["10001", "999999999", "12345678,50"])
def test_a_price_that_is_only_too_high_is_told_the_ceiling(world, price):
    users, clients=world
    response=clients[0].post("/new", data={"kind":"item","title":"Test","description":"A used desk", "price":price}, headers=ORIGIN)
    assert response.status_code==200
    assert "A price can be at most 10,000 euros." in response.text
    assert "plain number" not in response.text

def test_one_view_is_singular(world):
    users, clients=world
    listing=db.create_listing(users[0], "item", "A desk", price=20)
    with db.connect() as conn:
        conn.execute("UPDATE listings SET views=1 WHERE id=?", (listing,))
    conn.close()
    page=clients[0].get("/profile").text
    assert "1 view " in page or "1 view<" in page or "1 view ·" in page
    assert "1 views" not in page

def test_one_month_one_entry_one_chat_are_singular(world):
    users, clients=world
    room=db.create_listing(users[0], "housing", "A room", price=400)
    with db.connect() as conn:
        conn.execute("UPDATE listings SET months_min=1 WHERE id=?", (room,))
    conn.close()
    db.open_conversation(room, users[1])
    detail=clients[1].get(f"/listing/{room}").text
    assert "1 month" in detail and "1 months" not in detail
    housing=clients[1].get("/housing").text
    assert "1 month min" in housing and "1 months" not in housing
    profile=clients[0].get("/profile").text
    assert "<span>entry</span>" in profile and "<span>chat</span>" in profile

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

def test_the_development_login_is_gone_for_everybody(world):
    # It used to be a page listing every account, open whenever
    # CAMPUS_SECURITY_DEMO was set, which on a server is one wrong
    # environment variable away from handing out every student's chats.
    # There is no longer a setting that brings it back.
    import app.main as module
    client=TestClient(app)
    assert client.get("/dev").status_code==404
    assert client.post("/dev",data={"user_id":world[0][0]},headers=ORIGIN).status_code==404
    assert module.LOCAL_DEMO is True   # even with demo mode on
    assert not any(getattr(r,"path","")=="/dev" for r in app.routes)

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
        "address":"Test Street 1, 2775-123 Carcavelos", "deposit":"400", "months_min":"1", "minutes_campus":"10", "flatmates":"2",
    }, headers=ORIGIN)
    assert response.status_code == 200
    assert len(db.listings_of_user(users[0])) == before

def test_housing_fields_survive_valid_publication(world):
    users, clients = world
    response = clients[0].post("/new", data={
        "kind":"housing", "title":"New room", "price":"400", "bills_estimate":"35",
        "category":"shared_flat", "flatmates":"2", "available_from":"2027-02-01",
        "description":"A furnished room", "place":"carcavelos",
        "address":"Rua de Teste 1, 2775-000 Carcavelos",
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
    """Behind the proxy, https is believed from the proxy and nobody else.

    The whole question here is which address the request came from, because
    the proxy layer rewrites http to https only for an address it trusts,
    and the origin check then compares that scheme against the Origin
    header. The test client of this Starlette has no way to say what that
    address is, so we write it into the scope ourselves, one layer above
    the proxy. That is the same single value a newer test client would set
    for us; both assertions below are untouched.
    """
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
    proxied = ProxyHeadersMiddleware(app, trusted_hosts=["127.0.0.1"])

    def client_at(host):
        async def arriving_from(scope, receive, send):
            if scope["type"] == "http":
                scope = dict(scope, client=(host, 50000))
            await proxied(scope, receive, send)
        return TestClient(arriving_from)

    headers = {"origin": "https://testserver", "x-forwarded-proto": "https"}
    trusted = client_at("127.0.0.1")
    assert trusted.post("/logout", headers=headers, follow_redirects=False).status_code == 303
    untrusted = client_at("203.0.113.10")
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


def test_ticket_import_requires_origin_login_and_per_user_limit(world, monkeypatch):
    from app import ticket_import
    monkeypatch.setattr(ticket_import, "autofill", lambda url: {"ok": True, "fields": {"title":"Mock event"}})
    _, clients = world
    assert clients[0].post("/new/ticket-autofill", data={"url":"dice.fm/x"}).status_code == 403
    guest = TestClient(app)
    assert guest.post("/new/ticket-autofill", headers=ORIGIN).status_code == 401
    for _ in range(30):
        assert clients[0].post("/new/ticket-autofill", data={"url":"dice.fm/x"}, headers=ORIGIN).status_code == 200
    assert clients[0].post("/new/ticket-autofill", headers=ORIGIN).status_code == 429
    assert clients[1].post("/new/ticket-autofill", headers=ORIGIN).status_code == 200


def test_push_devices_reject_internal_and_unapproved_servers(world):
    _, clients = world
    for endpoint in ("https://127.0.0.1/x", "https://localhost/x", "https://evil.example/x",
                     "https://fcm.googleapis.com.evil.example/x", "https://fcm.googleapis.com:444/x",
                     "https://user:pass@fcm.googleapis.com/x"):
        response = clients[0].post("/push/device", headers=ORIGIN,
            json={"endpoint":endpoint,"keys":{"p256dh":"k","auth":"a"}})
        assert response.status_code == 400


def test_ai_quota_is_atomic_across_concurrent_requests(world):
    users, _ = world
    with ThreadPoolExecutor(max_workers=4) as pool:
        accepted = list(pool.map(lambda _: db.take_ai_read(users[0], 2), range(8)))
    assert accepted.count(True) == 2
    assert not db.take_ai_read(users[0], 2, -1)


def test_push_does_not_follow_redirects(monkeypatch):
    from app import push
    from requests import Session
    from types import SimpleNamespace
    device = {"user_id":1,"endpoint":"https://fcm.googleapis.com/fcm/send/mock","p256dh":"key","auth":"a"}
    def fake_webpush(**kwargs):
        kwargs["requests_session"].request("POST", device["endpoint"])
        return SimpleNamespace(status_code=302)
    with patch("pywebpush.webpush", side_effect=fake_webpush), patch.object(Session, "request") as request:
        assert push._webpush(device, {}) is False
        assert request.call_args.kwargs["allow_redirects"] is False
    with patch("pywebpush.webpush") as send:
        assert push._webpush(dict(device,endpoint="https://127.0.0.1/x"), {}) is False
        send.assert_not_called()


@pytest.mark.parametrize("endpoint", [
    "https://fcm.googleapis.com/fcm/send/mock",
    "https://updates.push.services.mozilla.com/wpush/v2/mock",
    "https://web.push.apple.com/mock",
    "https://wns2-test.notify.windows.com/mock",
])
def test_supported_browser_push_providers(endpoint):
    from app import push
    assert push.valid_endpoint(endpoint)


def test_ticket_keeps_a_known_link_and_refuses_the_rest(world):
    """A ticket stores its event link the same way a room stores its advert.

    Only a site on the ticket list gets through, and a housing link is not
    one, or the button on a ticket could send somebody to a flat.
    """
    users, clients = world
    good = {"kind": "ticket", "title": "Student night", "price": "12",
            "quantity": "1", "event_date": "2027-02-01", "event_time": "23:00",
            "place": "Urban Beach", "address": "Cais da Viscondessa, 1200-109 Lisboa",
            "description": "One ticket left", "category": "party",
            "external_url": "lu.ma/student-night"}
    assert clients[0].post("/new", data=good, headers=ORIGIN,
                           follow_redirects=False).status_code == 303
    kept = db.listings_of_user(users[0])[0]
    assert kept["external_url"] == "https://lu.ma/student-night"

    for bad in ("https://idealista.pt/imovel/1/", "https://evil.com/lu.ma"):
        before = len(db.listings_of_user(users[0]))
        response = clients[0].post(
            "/new", data=dict(good, title="Another", external_url=bad), headers=ORIGIN)
        assert response.status_code == 200
        assert "not from a ticket site we know" in response.text
        assert len(db.listings_of_user(users[0])) == before


def test_an_entry_can_lose_its_link_again(world):
    """external_url is editable, so a dead advert can be taken off."""
    users, clients = world
    fields = {"kind": "housing", "title": "A room", "price": "400",
              "bills_estimate": "35", "category": "shared_flat", "flatmates": "2",
              "available_from": "2027-02-01", "description": "A furnished room",
              "place": "carcavelos", "address": "Rua de Teste 1, 2775-000 Carcavelos",
              "deposit": "400", "months_min": "1", "minutes_campus": "10",
              "external_url": "badi.com/room/9"}
    assert clients[0].post("/new", data=fields, headers=ORIGIN,
                           follow_redirects=False).status_code == 303
    listing = db.listings_of_user(users[0])[0]
    assert listing["external_url"] == "https://badi.com/room/9"

    clients[0].post("/new", data=dict(fields, edit_id=str(listing["id"]),
                                      external_url=""), headers=ORIGIN,
                    follow_redirects=False)
    assert db.get_listing(listing["id"])["external_url"] is None
