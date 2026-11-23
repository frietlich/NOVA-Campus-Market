"""The full inbox stays scoped to its user and independent of listing filters."""
import pytest
from app import db
from test_desktop import world, ORIGIN


@pytest.mark.parametrize('path', ['/housing', '/tickets', '/market', '/groups'])
def test_categories_share_the_complete_inbox(world, path):
    html = world['clients'][1].get(path).text
    assert 'Search your chats' in html
    assert 'name="dock_q"' in html
    assert 'data-desktop-chat-overview' in html
    assert 'data-close-dock' not in html
    assert 'Is it still there?' in html


def test_chat_search_and_listing_search_are_independent(world):
    html = world['clients'][1].get('/market?q=NO_LISTING_MATCH&dock_q=still').text
    assert 'Is it still there?' in html
    assert 'name="q" type="search" value="NO_LISTING_MATCH"' in html
    assert 'name="dock_q" type="search" value="still"' in html
    assert f'/market?q=NO_LISTING_MATCH&amp;dock_q=still&amp;chat={world["conv"]}' in html
    hidden = world['clients'][1].get('/market?dock_q=NO_CHAT_MATCH').text
    assert 'Is it still there?' not in hidden
    assert 'No chat of yours matches that.' in hidden


def test_panel_does_not_limit_history_to_twelve_chats(world):
    for n in range(14):
        listing = db.create_listing(world['users'][0], 'item', f'History entry {n}', price=1)
        conv = db.open_conversation(listing, world['users'][1])
        db.send_message(conv, world['users'][1], f'History message {n}')
    html = world['clients'][1].get('/market').text
    assert 'History entry 0' in html and 'History entry 13' in html
    assert 'History message 0' not in world['clients'][2].get('/market').text


def test_panel_updates_filter_private_records_and_keep_category_location(world):
    client = world['clients'][1]
    response = client.get('/chats/updates', params={'page_url': '/tickets?cat=party&dock_q=still'})
    html = response.json()['overview_html']
    assert 'Is it still there?' in html
    assert f'/tickets?cat=party&amp;dock_q=still&amp;chat={world["conv"]}' in html
    assert 'Is it still there?' not in world['clients'][2].get('/chats/updates').json()['overview_html']
    assert not db.messages_of(world['conv'])[0]['read_at']
    assert 'Is it still there?' not in client.get('/chats/updates', params={
        'page_url': '/market?dock_q=not-a-message'}).json()['overview_html']


def test_archive_returns_to_category_but_rejects_external_returns(world):
    client, conv = world['clients'][1], world['conv']
    assert 'aria-label="Archive this chat"' in client.get(f'/market?chat={conv}').text
    result = client.post(f'/chat/{conv}/archive?back=/market?dock_side=buy',
                         headers=ORIGIN, follow_redirects=False)
    assert result.headers['location'] == '/market?dock_side=buy'
    archived = client.get('/market?dock_side=buy&dock_archived=1').text
    assert 'Is it still there?' in archived
    assert 'Back to your chats' in archived
    assert 'Take this chat out of your archive' in client.get(f'/market?dock_archived=1&chat={conv}').text
    result = client.post(f'/chat/{conv}/unarchive?back=//outside.invalid',
                         headers=ORIGIN, follow_redirects=False)
    assert result.headers['location'] == '/chats?side=buy'


def test_standalone_phone_inbox_still_uses_its_normal_urls(world):
    html = world['clients'][1].get('/chats').text
    assert 'action="/chats"' in html
    assert 'id="q" name="q"' in html
    assert f'href="/chat/{world["conv"]}"' in html
    assert 'data-desktop-chat-overview' not in html
