import json, urllib.request, os

TOKEN = os.environ["SHOPIFY_ADMIN_TOKEN"]
DOMAIN = "amsterdam-baking-company.myshopify.com"

req = urllib.request.Request(
    f"https://{DOMAIN}/admin/api/2024-10/products.json?limit=50",
    headers={"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"}
)
resp = urllib.request.urlopen(req)
products = json.loads(resp.read())["products"]

for p in products:
    print(f"### {p['id']} — {p['title']}")
    print(f"  Type: {p.get('product_type', '')}")
    if p.get("options"):
        for o in p["options"]:
            print(f"  Option: {o['name']} = {o['values']}")
    for v in p.get("variants", []):
        print(f"  Variant: id={v['id']} title='{v['title']}' price={v['price']} sku={v.get('sku', '')}")
    print()
