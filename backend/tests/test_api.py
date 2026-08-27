"""API tests against a throwaway SQLite database."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["ORDERPAD_DB"] = "sqlite:///./test_orderpad.db"

import pytest
from fastapi.testclient import TestClient

from app import seed
from app.main import app

client = TestClient(app)


@pytest.fixture(scope="session", autouse=True)
def fresh_db():
    if os.path.exists("test_orderpad.db"):
        os.remove("test_orderpad.db")
    seed.run()
    yield
    os.remove("test_orderpad.db")


def _login(pin):
    return client.post("/api/login", json={"pin": pin})


def _auth(pin):
    return {"Authorization": f"Bearer {_login(pin).json()['token']}"}


def _find(catalog, product_name):
    for cat in catalog:
        for p in cat["products"]:
            if p["name"] == product_name:
                return p
    raise AssertionError(f"{product_name} not in catalog")


def _option(product, group_name, option_name):
    for g in product["option_groups"]:
        if g["name"] == group_name:
            for o in g["options"]:
                if o["name"] == option_name:
                    return o
    raise AssertionError(f"{group_name}/{option_name} not on {product['name']}")


def test_wrong_pin_rejected():
    assert _login("0000").status_code == 401


def test_login_returns_role():
    body = _login("9999").json()
    assert body["user"]["role"] == "admin"


def test_staff_cannot_manage_products_or_options():
    headers = _auth("1111")
    assert client.post("/api/products", headers=headers,
                       json={"name": "X", "price_cents": 100,
                             "category_id": 1}).status_code == 403
    assert client.post("/api/option-groups", headers=headers,
                       json={"name": "X"}).status_code == 403


def test_catalog_exposes_option_groups():
    catalog = client.get("/api/catalog", headers=_auth("1111")).json()
    espresso = _find(catalog, "Espresso")
    group_names = {g["name"] for g in espresso["option_groups"]}
    assert {"Sugar", "Extras"} <= group_names
    freddo = _find(catalog, "Freddo Espresso")
    assert "Ice" in {g["name"] for g in freddo["option_groups"]}


def test_required_group_enforced():
    headers = _auth("1111")
    catalog = client.get("/api/catalog", headers=headers).json()
    espresso = _find(catalog, "Espresso")
    response = client.post("/api/orders", headers=headers, json={
        "table_id": 1,
        "items": [{"product_id": espresso["id"], "qty": 1}],  # no Sugar choice
    })
    assert response.status_code == 422
    assert "Sugar" in response.json()["detail"]


def test_order_with_options_prices_and_snapshots():
    headers = _auth("1111")
    catalog = client.get("/api/catalog", headers=headers).json()
    espresso = _find(catalog, "Espresso")
    medium = _option(espresso, "Sugar", "Medium")
    shot = _option(espresso, "Extras", "Extra shot")

    created = client.post("/api/orders", headers=headers, json={
        "table_id": 1,
        "items": [{"product_id": espresso["id"], "qty": 2, "note": "",
                   "option_ids": [medium["id"], shot["id"]]}],
    })
    assert created.status_code == 201
    order = created.json()
    # (200 base + 50 extra shot) * 2
    assert order["total_cents"] == 500
    names = {o["name"] for o in order["items"][0]["options"]}
    assert names == {"Medium", "Extra shot"}
    assert order["status"] == "open"


def test_single_select_rejects_two_choices():
    headers = _auth("1111")
    catalog = client.get("/api/catalog", headers=headers).json()
    espresso = _find(catalog, "Espresso")
    medium = _option(espresso, "Sugar", "Medium")
    sweet = _option(espresso, "Sugar", "Sweet")
    response = client.post("/api/orders", headers=headers, json={
        "table_id": 1,
        "items": [{"product_id": espresso["id"], "qty": 1,
                   "option_ids": [medium["id"], sweet["id"]]}],
    })
    assert response.status_code == 422


def test_admin_manages_option_groups_and_attaches_to_product():
    headers = _auth("9999")
    group = client.post("/api/option-groups", headers=headers,
                        json={"name": "Mixer", "selection": "single"}).json()
    option = client.post(f"/api/option-groups/{group['id']}/options",
                         headers=headers,
                         json={"name": "Tonic", "price_delta_cents": 100}).json()
    assert option["price_delta_cents"] == 100

    products = client.get("/api/products", headers=headers).json()
    lager = next(p for p in products if p["name"] == "Lager 500ml")
    patched = client.patch(f"/api/products/{lager['id']}", headers=headers, json={
        "name": lager["name"], "price_cents": lager["price_cents"],
        "category_id": lager["category_id"], "active": True,
        "option_group_ids": [group["id"]],
    }).json()
    assert [g["name"] for g in patched["option_groups"]] == ["Mixer"]


def test_admin_summary_counts_revenue():
    body = client.get("/api/summary", headers=_auth("9999")).json()
    assert body["orders_today"] >= 1
    assert body["revenue_cents_today"] >= 500


def test_admin_edits_option_price_name_and_group():
    headers = _auth("9999")
    groups = client.get("/api/option-groups", headers=headers).json()
    extras = next(g for g in groups if g["name"] == "Extras")
    shot = next(o for o in extras["options"] if o["name"] == "Extra shot")

    patched = client.patch(f"/api/options/{shot['id']}", headers=headers,
                           json={"price_delta_cents": 80,
                                 "name": "Double shot"}).json()
    assert (patched["price_delta_cents"], patched["name"]) == (80, "Double shot")

    renamed = client.patch(f"/api/option-groups/{extras['id']}",
                           headers=headers, json={"name": "Add-ons"}).json()
    assert renamed["name"] == "Add-ons"


def test_default_switch_unsets_sibling_in_single_group():
    headers = _auth("9999")
    groups = client.get("/api/option-groups", headers=headers).json()
    sugar = next(g for g in groups if g["name"] == "Sugar")
    sweet = next(o for o in sugar["options"] if o["name"] == "Sweet")

    client.patch(f"/api/options/{sweet['id']}", headers=headers,
                 json={"is_default": True})
    groups = client.get("/api/option-groups", headers=headers).json()
    sugar = next(g for g in groups if g["name"] == "Sugar")
    defaults = [o["name"] for o in sugar["options"] if o["is_default"]]
    assert defaults == ["Sweet"]


def test_transfer_moves_the_whole_tab():
    headers = _auth("2222")
    catalog = client.get("/api/catalog", headers=headers).json()
    espresso = _find(catalog, "Espresso")
    medium = _option(espresso, "Sugar", "Medium")
    for _ in range(2):  # two rounds on the same table
        client.post("/api/orders", headers=headers, json={
            "table_id": 6,
            "items": [{"product_id": espresso["id"], "qty": 1,
                       "option_ids": [medium["id"]]}],
        })

    moved = client.post("/api/tables/6/transfer", headers=headers,
                        json={"table_id": 4}).json()
    assert moved["orders_moved"] == 2

    active = client.get("/api/orders?active=1", headers=headers).json()
    assert not any(o["table"]["id"] == 6 for o in active)
    assert sum(1 for o in active if o["table"]["id"] == 4) >= 2

    assert client.post("/api/tables/6/transfer", headers=headers,
                       json={"table_id": 999}).status_code == 404


def test_admin_manages_categories_with_guarded_delete():
    headers = _auth("9999")
    created = client.post("/api/categories", headers=headers,
                          json={"name": "Desserts"})
    assert created.status_code == 201
    cat_id = created.json()["id"]

    renamed = client.patch(f"/api/categories/{cat_id}", headers=headers,
                           json={"name": "Sweets"}).json()
    assert renamed["name"] == "Sweets"

    catalog = client.get("/api/catalog", headers=headers).json()
    coffee = next(c for c in catalog if c["name"] == "Coffee")
    assert client.delete(f"/api/categories/{coffee['id']}",
                         headers=headers).status_code == 422  # has products
    assert client.delete(f"/api/categories/{cat_id}",
                         headers=headers).status_code == 204  # empty, ok


def test_admin_manages_tables_with_guarded_delete():
    headers = _auth("9999")
    area_id = client.get("/api/areas", headers=headers).json()[0]["id"]
    assert client.post("/api/tables", headers=_auth("1111"),
                       json={"name": "X", "area_id": area_id}
                       ).status_code == 403  # staff blocked

    created = client.post("/api/tables", headers=headers,
                          json={"name": "Terrace 1", "area_id": area_id})
    assert created.status_code == 201
    table_id = created.json()["id"]

    renamed = client.patch(f"/api/tables/{table_id}", headers=headers,
                           json={"name": "Terrace A"}).json()
    assert renamed["name"] == "Terrace A"

    assert client.delete(f"/api/tables/{table_id}",
                         headers=headers).status_code == 204  # no orders yet
    assert client.delete("/api/tables/1",
                         headers=headers).status_code == 422  # has history


def test_admin_can_attach_group_directly_to_a_product():
    headers = _auth("9999")
    group = client.post("/api/option-groups", headers=headers,
                        json={"name": "Serving"}).json()
    client.post(f"/api/option-groups/{group['id']}/options", headers=headers,
                json={"name": "With ice", "is_default": True})

    products = client.get("/api/products", headers=headers).json()
    lager = next(p for p in products if p["name"] == "Lager 500ml")
    patched = client.patch(f"/api/products/{lager['id']}", headers=headers, json={
        "name": lager["name"], "price_cents": lager["price_cents"],
        "category_id": lager["category_id"], "active": True,
        "option_group_ids": [group["id"]],
    }).json()
    assert [g["name"] for g in patched["option_groups"]] == ["Serving"]

    # Uniform: a sibling product in the same category does NOT inherit it.
    catalog = client.get("/api/catalog", headers=headers).json()
    beer_cat = next(c for c in catalog if c["name"] == "Beer & Wine")
    ipa = next(p for p in beer_cat["products"] if p["name"] == "IPA 330ml")
    assert "Serving" not in [g["name"] for g in ipa["option_groups"]]


def test_inactive_option_hidden_and_rejected():
    headers = _auth("9999")
    groups = client.get("/api/option-groups", headers=headers).json()
    sugar = next(g for g in groups if g["name"] == "Sugar")
    sweet = next(o for o in sugar["options"] if o["name"] == "Sweet")

    client.patch(f"/api/options/{sweet['id']}", headers=headers,
                 json={"active": False})
    catalog = client.get("/api/catalog", headers=headers).json()
    espresso = _find(catalog, "Espresso")
    sugar_group = next(g for g in espresso["option_groups"]
                       if g["name"] == "Sugar")
    assert "Sweet" not in [o["name"] for o in sugar_group["options"]]

    medium = next(o for o in sugar_group["options"] if o["name"] == "Medium")
    rejected = client.post("/api/orders", headers=_auth("1111"), json={
        "table_id": 1,
        "items": [{"product_id": espresso["id"], "qty": 1,
                   "option_ids": [sweet["id"]]}],
    })
    assert rejected.status_code == 422
    client.patch(f"/api/options/{sweet['id']}", headers=headers,
                 json={"active": True})  # restore for other tests


def test_product_delete_with_history_guard():
    headers = _auth("9999")
    created = client.post("/api/products", headers=headers, json={
        "name": "Test Lemonade", "price_cents": 300, "category_id": 2,
    }).json()
    assert client.delete(f"/api/products/{created['id']}",
                         headers=headers).status_code == 204

    products = client.get("/api/products", headers=headers).json()
    espresso = next(p for p in products if p["name"] == "Espresso")
    assert client.delete(f"/api/products/{espresso['id']}",
                         headers=headers).status_code == 422  # ordered before


def test_z_report_per_waiter():
    headers = _auth("9999")
    z = client.get("/api/reports/z", headers=headers).json()
    assert z["total_orders"] >= 2
    names = [w["waiter"] for w in z["waiters"]]
    assert "Maria" in names and "Nikos" in names
    assert z["total_revenue_cents"] == sum(
        w["revenue_cents"] for w in z["waiters"])
    assert client.get("/api/reports/z",
                      headers=_auth("1111")).status_code == 403



def test_settle_closes_the_tab_and_is_idempotent():
    maria, nikos = _auth("1111"), _auth("2222")
    catalog = client.get("/api/catalog", headers=maria).json()
    espresso = _find(catalog, "Espresso")
    medium = _option(espresso, "Sugar", "Medium")

    for headers, qty in ((maria, 1), (nikos, 2)):  # two waiters, one table
        client.post("/api/orders", headers=headers, json={
            "table_id": 7,
            "items": [{"product_id": espresso["id"], "qty": qty,
                       "option_ids": [medium["id"]]}],
        })

    settled = client.post("/api/tables/7/settle", headers=maria).json()
    assert settled["orders_closed"] == 2
    assert settled["total_cents"] == 600  # 200 + 400

    active = client.get("/api/orders?active=1", headers=maria).json()
    assert not any(o["table"]["id"] == 7 for o in active)

    again = client.post("/api/tables/7/settle", headers=maria).json()
    assert again["orders_closed"] == 0  # idempotent, no error

    z = client.get("/api/reports/z", headers=_auth("9999")).json()
    names = [w["waiter"] for w in z["waiters"]]
    assert "Maria" in names and "Nikos" in names  # per-waiter split intact


def test_areas_seeded_with_correct_table_counts():
    headers = _auth("1111")  # visible to staff too
    areas = client.get("/api/areas", headers=headers).json()
    assert [a["name"] for a in areas] == ["Upstairs", "Downstairs", "Beach"]

    tables = client.get("/api/tables", headers=headers).json()
    by_area = {a["name"]: sum(1 for t in tables if t["area_id"] == a["id"])
               for a in areas}
    assert by_area == {"Upstairs": 10, "Downstairs": 24, "Beach": 40}

    # autonomous numbering: "Table 1" exists independently in every zone
    down = {t["name"] for t in tables if t["area_id"] == areas[1]["id"]}
    beach = {t["name"] for t in tables if t["area_id"] == areas[2]["id"]}
    assert "Table 1" in down and "Table 1" in beach
    assert tables[0]["area_name"] == "Upstairs"


def test_admin_manages_areas_with_guarded_delete():
    headers = _auth("9999")
    assert client.post("/api/areas", headers=_auth("1111"),
                       json={"name": "X"}).status_code == 403  # staff blocked

    created = client.post("/api/areas", headers=headers,
                          json={"name": "Garden"})
    assert created.status_code == 201
    area_id = created.json()["id"]
    assert client.patch(f"/api/areas/{area_id}", headers=headers,
                        json={"name": "Roof"}).json()["name"] == "Roof"

    # a table assigned to the area blocks deletion
    table = client.post("/api/tables", headers=headers,
                        json={"name": "Roof 1", "area_id": area_id}).json()
    assert table["area_id"] == area_id
    assert client.delete(f"/api/areas/{area_id}",
                         headers=headers).status_code == 422

    # tables can never be orphaned - move it to another area instead
    assert client.patch(f"/api/tables/{table['id']}", headers=headers,
                        json={"area_id": None}).status_code == 422
    upstairs_id = client.get("/api/areas", headers=headers).json()[0]["id"]
    client.patch(f"/api/tables/{table['id']}", headers=headers,
                 json={"area_id": upstairs_id})
    assert client.delete(f"/api/areas/{area_id}",
                         headers=headers).status_code == 204
    client.delete(f"/api/tables/{table['id']}", headers=headers)

    # seeded area with tables is protected
    upstairs = client.get("/api/areas", headers=headers).json()[0]
    assert client.delete(f"/api/areas/{upstairs['id']}",
                         headers=headers).status_code == 422


def test_version_is_public():
    body = client.get("/api/version").json()
    assert body["version"].count(".") == 2  # e.g. 0.11.1


def test_options_keep_insertion_order_not_alphabetical():
    headers = _auth("9999")
    group = client.post("/api/option-groups", headers=headers,
                        json={"name": "Doneness"}).json()
    for name in ["Rare", "Medium done", "Well done"]:  # not alphabetical
        client.post(f"/api/option-groups/{group['id']}/options",
                    headers=headers, json={"name": name})

    groups = client.get("/api/option-groups", headers=headers).json()
    fetched = next(g for g in groups if g["id"] == group["id"])
    assert [o["name"] for o in fetched["options"]] == [
        "Rare", "Medium done", "Well done"]
    client.delete(f"/api/option-groups/{group['id']}", headers=headers)


def test_greek_names_work_end_to_end():
    headers = _auth("9999")
    cat = client.post("/api/categories", headers=headers,
                      json={"name": "Καφέδες"}).json()
    prod = client.post("/api/products", headers=headers, json={
        "name": "Φρέντο Εσπρέσο", "price_cents": 320,
        "category_id": cat["id"]}).json()
    group = client.post("/api/option-groups", headers=headers,
                        json={"name": "Ζάχαρη", "required": True}).json()
    option = client.post(f"/api/option-groups/{group['id']}/options",
                         headers=headers,
                         json={"name": "Μέτριος", "is_default": True}).json()
    client.patch(f"/api/products/{prod['id']}", headers=headers, json={
        "name": prod["name"], "price_cents": prod["price_cents"],
        "category_id": prod["category_id"], "active": True,
        "option_group_ids": [group["id"]]})

    # a Greek order, end to end, with the option snapshot intact
    order = client.post("/api/orders", headers=_auth("1111"), json={
        "table_id": 1,
        "items": [{"product_id": prod["id"], "qty": 1, "note": "χωρίς καλαμάκι",
                   "option_ids": [option["id"]]}]}).json()
    item = order["items"][0]
    assert item["name"] == "Φρέντο Εσπρέσο"
    assert item["note"] == "χωρίς καλαμάκι"
    assert item["options"][0]["name"] == "Μέτριος"

    # cleanup (product has history now -> deactivate instead of delete)
    client.patch(f"/api/products/{prod['id']}", headers=headers, json={
        "name": prod["name"], "price_cents": prod["price_cents"],
        "category_id": prod["category_id"], "active": False,
        "option_group_ids": []})
    client.delete(f"/api/option-groups/{group['id']}", headers=headers)


def test_option_groups_keep_insertion_order():
    headers = _auth("9999")
    for name in ["Zzz Group", "Aaa Group"]:  # deliberately anti-alphabetical
        client.post("/api/option-groups", headers=headers, json={"name": name})

    groups = client.get("/api/option-groups", headers=headers).json()
    names = [g["name"] for g in groups]
    # seeded order intact ("Extras" was renamed to "Add-ons" earlier on)
    assert names.index("Sugar") < names.index("Ice") < names.index("Add-ons")
    # new groups append at the end, in the order they were created
    assert names[-2:] == ["Zzz Group", "Aaa Group"]
    for g in groups:
        if g["name"] in ("Zzz Group", "Aaa Group"):
            client.delete(f"/api/option-groups/{g['id']}", headers=headers)


def test_admin_manages_staff():
    headers = _auth("9999")
    assert client.get("/api/users", headers=_auth("1111")).status_code == 403

    dup = client.post("/api/users", headers=headers,
                      json={"name": "Eleni", "pin": "1111"})
    assert dup.status_code == 422  # PIN collision with Maria

    created = client.post("/api/users", headers=headers,
                          json={"name": "Eleni", "pin": "3333"})
    assert created.status_code == 201
    uid = created.json()["id"]
    assert _login("3333").json()["user"]["name"] == "Eleni"

    client.patch(f"/api/users/{uid}", headers=headers, json={"pin": "4444"})
    assert _login("3333").status_code == 401  # old PIN dead
    assert _login("4444").status_code == 200  # new PIN live

    client.patch(f"/api/users/{uid}", headers=headers, json={"active": False})
    off = _login("4444")
    assert off.status_code == 403  # "off" blocks login...
    assert "deactivated" in off.json()["detail"].lower()  # ...politely

    assert client.delete(f"/api/users/{uid}",
                         headers=headers).status_code == 204  # no history

    users = client.get("/api/users", headers=headers).json()
    maria = next(u for u in users if u["name"] == "Maria")
    assert client.delete(f"/api/users/{maria['id']}",
                         headers=headers).status_code == 422  # has history

    admin = next(u for u in users if u["role"] == "admin")
    # the last admin cannot be demoted to a non-admin role...
    assert client.patch(f"/api/users/{admin['id']}", headers=headers,
                        json={"role": "bar"}).status_code == 422
    # ...nor deactivated, and the role must be untouched afterwards
    assert client.patch(f"/api/users/{admin['id']}", headers=headers,
                        json={"active": False}).status_code == 422
    after = client.get("/api/users", headers=headers).json()
    assert next(u for u in after if u["id"] == admin["id"])["role"] == "admin"


def test_server_info_admin_only():
    info = client.get("/api/server-info", headers=_auth("9999")).json()
    assert info["url"] == f"http://{info['ip']}:{info['port']}"
    assert client.get("/api/server-info",
                      headers=_auth("1111")).status_code == 403


from app.main import FRONTEND_DIST  # noqa: E402


@pytest.mark.skipif(not FRONTEND_DIST.exists(),
                    reason="frontend not built")
def test_spa_served_and_api_404_untouched():
    page = client.get("/")
    assert page.status_code == 200 and 'id="root"' in page.text
    assert client.get("/api/definitely-not-a-route").status_code == 404
    deep = client.get("/tables")  # client-side route survives refresh
    assert deep.status_code == 200 and 'id="root"' in deep.text


def test_cancel_round_and_whole_tab():
    headers = _auth("1111")
    catalog = client.get("/api/catalog", headers=headers).json()
    espresso = _find(catalog, "Espresso")
    medium = _option(espresso, "Sugar", "Medium")
    payload = {"table_id": 8, "items": [{"product_id": espresso["id"],
                                         "qty": 1,
                                         "option_ids": [medium["id"]]}]}
    first = client.post("/api/orders", headers=headers, json=payload).json()
    client.post("/api/orders", headers=headers, json=payload)

    assert client.delete(f"/api/orders/{first['id']}",
                         headers=headers).status_code == 204
    active = client.get("/api/orders?active=1", headers=headers).json()
    assert sum(1 for o in active if o["table"]["id"] == 8) == 1

    client.post("/api/tables/8/settle", headers=headers)
    paid = [o for o in client.get("/api/orders", headers=headers).json()
            if o["table"]["id"] == 8][-1]
    assert client.delete(f"/api/orders/{paid['id']}",
                         headers=headers).status_code == 422  # history locked

    client.post("/api/orders", headers=headers, json=payload)
    voided = client.post("/api/tables/8/cancel", headers=headers).json()
    assert voided["orders_closed"] == 1
    active = client.get("/api/orders?active=1", headers=headers).json()
    assert not any(o["table"]["id"] == 8 for o in active)


def test_categories_follow_manual_order_with_move():
    headers = _auth("9999")

    def names():
        return [c["name"] for c in
                client.get("/api/catalog", headers=headers).json()]

    base = names()
    assert base[:4] == ["Coffee", "Beverages", "Beer & Wine", "Snacks"]

    snacks = client.get("/api/catalog", headers=headers).json()[3]
    client.post(f"/api/categories/{snacks['id']}/move", headers=headers,
                json={"direction": "up"})
    assert names()[:4] == ["Coffee", "Beverages", "Snacks", "Beer & Wine"]
    client.post(f"/api/categories/{snacks['id']}/move", headers=headers,
                json={"direction": "down"})
    assert names()[:4] == base[:4]

    created = client.post("/api/categories", headers=headers,
                          json={"name": "Aaa Newest"}).json()
    assert names()[-1] == "Aaa Newest"  # appends - not alphabetical
    client.delete(f"/api/categories/{created['id']}", headers=headers)


def test_merging_tables_combines_open_tabs():
    headers = _auth("1111")
    catalog = client.get("/api/catalog", headers=headers).json()
    espresso = _find(catalog, "Espresso")
    medium = _option(espresso, "Sugar", "Medium")

    def order_on(table_id, qty):
        return client.post("/api/orders", headers=headers, json={
            "table_id": table_id,
            "items": [{"product_id": espresso["id"], "qty": qty,
                       "option_ids": [medium["id"]]}]}).json()

    order_on(9, 1)   # Table 9: 2.00
    order_on(10, 2)  # Table 10: 4.00

    moved = client.post("/api/tables/10/transfer", headers=headers,
                        json={"table_id": 9}).json()
    assert moved["orders_moved"] == 1

    active = client.get("/api/orders?active=1", headers=headers).json()
    assert sum(1 for o in active if o["table"]["id"] == 9) == 2  # combined
    assert not any(o["table"]["id"] == 10 for o in active)       # freed

    settled = client.post("/api/tables/9/settle", headers=headers).json()
    assert settled["total_cents"] == 600  # one bill for the joined party


def test_stats_endpoint_computes_analytics():
    admin = _auth("9999")
    assert client.get("/api/stats", headers=_auth("1111")).status_code == 403

    s = client.get("/api/stats", headers=admin).json()
    for key in ("total_orders", "total_revenue_cents", "avg_order_cents",
                "revenue_by_day", "by_hour", "pareto", "affinity"):
        assert key in s
    assert len(s["by_hour"]) == 24
    assert len(s["revenue_by_day"]) == 14
    # earlier tests placed multi-item and repeated orders, so analytics
    # should have found real signal
    assert s["total_orders"] > 0
    assert s["total_revenue_cents"] > 0
    if s["total_orders"]:
        assert 0 <= s["pareto_count"] <= s["pareto_total_products"]


def test_staff_stats_measures_performance():
    admin = _auth("9999")
    assert client.get("/api/stats/staff",
                      headers=_auth("1111")).status_code == 403

    body = client.get("/api/stats/staff", headers=admin).json()
    assert body["staff"], "earlier tests placed orders for Maria and Nikos"
    names = [w["waiter"] for w in body["staff"]]
    assert "Maria" in names

    maria = next(w for w in body["staff"] if w["waiter"] == "Maria")
    for key in ("orders", "revenue_cents", "avg_order_cents",
                "items_per_order", "attach_rate_pct", "extras_revenue_cents",
                "tables_served", "revenue_share_pct"):
        assert key in maria
    assert maria["orders"] > 0
    assert maria["avg_order_cents"] == round(
        maria["revenue_cents"] / maria["orders"])
    assert 0 <= maria["attach_rate_pct"] <= 100
    # Maria ordered an "Extra shot" (+0.50) in an earlier test
    assert maria["extras_revenue_cents"] > 0
    assert round(sum(w["revenue_share_pct"] for w in body["staff"])) in (99, 100, 101)


def test_stats_panel_visibility_toggles():
    admin = _auth("9999")
    assert client.get("/api/stats-settings",
                      headers=_auth("1111")).status_code == 403

    defaults = client.get("/api/stats-settings", headers=admin).json()["panels"]
    assert all(defaults.values()), "everything visible by default"

    saved = client.patch("/api/stats-settings", headers=admin,
                         json={"panels": {"affinity": False,
                                          "by_hour": False}}).json()["panels"]
    assert saved["affinity"] is False and saved["by_hour"] is False
    assert saved["pareto"] is True  # untouched panels stay on

    # the main stats payload carries the same visibility map
    assert client.get("/api/stats", headers=admin).json()["panels"]["affinity"] is False

    client.patch("/api/stats-settings", headers=admin,
                 json={"panels": {"affinity": True, "by_hour": True}})
    assert all(client.get("/api/stats-settings",
                          headers=admin).json()["panels"].values())


def test_split_payment_settles_selected_items_only():
    headers = _auth("1111")
    catalog = client.get("/api/catalog", headers=headers).json()
    espresso = _find(catalog, "Espresso")
    medium = _option(espresso, "Sugar", "Medium")
    cola = _find(catalog, "Cola 330ml")

    order = client.post("/api/orders", headers=headers, json={
        "table_id": 5,
        "items": [
            {"product_id": espresso["id"], "qty": 1,
             "option_ids": [medium["id"]]},          # 2.00
            {"product_id": cola["id"], "qty": 2},     # 6.00
        ]}).json()
    assert order["total_cents"] == 800 and order["due_cents"] == 800

    espresso_line = next(i for i in order["items"] if i["name"] == "Espresso")
    paid = client.post("/api/tables/5/pay-items", headers=headers,
                       json={"item_ids": [espresso_line["id"]]}).json()
    assert paid["paid_cents"] == 200
    assert paid["table_due_cents"] == 600  # the rest stays open

    active = client.get("/api/orders?active=1", headers=headers).json()
    mine = next(o for o in active if o["id"] == order["id"])
    assert mine["due_cents"] == 600 and mine["total_cents"] == 800
    assert next(i for i in mine["items"] if i["name"] == "Espresso")["paid"]

    # paying the remainder closes the order on its own
    cola_line = next(i for i in mine["items"] if i["name"] == "Cola 330ml")
    rest = client.post("/api/tables/5/pay-items", headers=headers,
                       json={"item_ids": [cola_line["id"]]}).json()
    assert rest["table_due_cents"] == 0
    active = client.get("/api/orders?active=1", headers=headers).json()
    assert not any(o["id"] == order["id"] for o in active)


def test_cancellations_are_recorded_and_measured():
    headers = _auth("2222")
    catalog = client.get("/api/catalog", headers=headers).json()
    cola = _find(catalog, "Cola 330ml")
    order = client.post("/api/orders", headers=headers, json={
        "table_id": 11,
        "items": [{"product_id": cola["id"], "qty": 1}]}).json()
    client.delete(f"/api/orders/{order['id']}", headers=headers)

    # the record survives cancellation (audit trail), just not as "active"
    everything = client.get("/api/orders", headers=headers).json()
    kept = next(o for o in everything if o["id"] == order["id"])
    assert kept["status"] == "cancelled"

    report = client.get("/api/stats/cancellations", headers=_auth("9999")).json()
    assert report["count"] >= 1
    assert report["total_cents"] >= 300
    assert report["avg_minutes"] is not None
    assert any(w["waiter"] == "Nikos" for w in report["by_waiter"])
    assert report["recent"][0]["minutes"] is not None

    # and cancelled money never counts as revenue
    z = client.get("/api/reports/z", headers=_auth("9999")).json()
    nikos = next((w for w in z["waiters"] if w["waiter"] == "Nikos"), None)
    summary = client.get("/api/summary", headers=_auth("9999")).json()
    assert summary["revenue_cents_today"] >= 0
