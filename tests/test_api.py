def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_landing_page(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "RetailIQ" in res.text


def test_login_page(client):
    res = client.get("/login")
    assert res.status_code == 200
    assert "Log In" in res.text


def test_dashboard_redirect_unauthenticated(client):
    res = client.get("/dashboard", follow_redirects=False)
    assert res.status_code == 302
    assert "/login" in res.headers["location"]


def test_dashboard_authenticated(client, auth_headers):
    # Set cookie from the token
    token = auth_headers["Authorization"].split(" ")[1]
    client.cookies.set("access_token", token)
    res = client.get("/dashboard")
    assert res.status_code == 200
    assert "Overview" in res.text


def test_dashboard_summary_api(client, auth_headers):
    res = client.get("/api/dashboard/summary", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "revenue_today" in data
    assert "transactions_today" in data


def test_dashboard_sales_api(client, auth_headers):
    res = client.get("/api/dashboard/sales?days=7", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "daily" in data


def test_dashboard_products_api(client, auth_headers):
    res = client.get("/api/dashboard/products", headers=auth_headers)
    assert res.status_code == 200
    assert "top_products" in res.json()


def test_dashboard_customers_api(client, auth_headers):
    res = client.get("/api/dashboard/customers", headers=auth_headers)
    assert res.status_code == 200
    assert "total_customers" in res.json()


def test_dashboard_competitors_api(client, auth_headers):
    res = client.get("/api/dashboard/competitors", headers=auth_headers)
    assert res.status_code == 200
    assert "competitors" in res.json()


def test_dashboard_reviews_api(client, auth_headers):
    res = client.get("/api/dashboard/reviews", headers=auth_headers)
    assert res.status_code == 200
    assert "reviews" in res.json()


def test_dashboard_alerts_api(client, auth_headers):
    res = client.get("/api/dashboard/alerts", headers=auth_headers)
    assert res.status_code == 200
    assert "alerts" in res.json()
    assert "unread_count" in res.json()


def test_api_unauthenticated(client):
    res = client.get("/api/dashboard/summary")
    assert res.status_code == 401
