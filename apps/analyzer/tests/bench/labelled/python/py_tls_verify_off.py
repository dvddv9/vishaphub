import requests

API = "https://billing.internal.example.com/v1/invoices"


def fetch_invoices(token):
    resp = requests.get(API, headers={"Authorization": f"Bearer {token}"}, verify=False, timeout=10)
    resp.raise_for_status()
    return resp.json()
