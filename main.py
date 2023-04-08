import json
import os
from dataclasses import dataclass
from typing import Dict, List

import quart
import quart_cors
import requests
from quart import request

# Note: Setting CORS to allow chat.openapi.com is required for ChatGPT to access your plugin
app = quart_cors.cors(quart.Quart(__name__), allow_origin="https://chat.openai.com")

_TAXAS = {}
BASE_URL = "https://oregonflora.org/"


@dataclass
class Taxa:
    tid: int
    family: str
    sciname: str
    parenttid: int
    author: str
    imgid: int
    vernacular: dict
    image: str

    @property
    def vernacular_basename(self) -> str:
        return self.vernacular.get('basename', '')

    @property
    def vernacular_names(self) -> List[str]:
        return self.vernacular.get('names', [])


def parse_taxa_by_tid(json_data: str) -> Dict[int, Taxa]:
    data = json.loads(json_data)
    taxa_dict = {}

    for taxa in data["taxa"]:
        tid = taxa["tid"]
        family = taxa["family"]
        sciname = taxa["sciname"]
        parenttid = taxa["parenttid"]
        author = taxa["author"]
        imgid = taxa["imgid"]
        vernacular_basename = taxa["vernacular"]["basename"]
        vernacular_names = taxa["vernacular"]["names"]
        image = BASE_URL + taxa["image"]

        taxa_dict[tid] = Taxa(tid, family, sciname, parenttid, author, imgid,
                              vernacular_basename, vernacular_names, image)

    return taxa_dict


def get_taxa_by_tid(tid: int) -> Taxa:
    return _TAXAS[tid]


@app.post("/search")
async def search():
    req = await request.get_json(force=True)
    base_url = "https://oregonflora.org/garden/rpc/api.php"
    params = {"clid": 54, "pid": 3}

    print("got req", req)

    for key, value in req.items():
        if 'attr[]' not in params:
            params['attr[]'] = []
        params['attr[]'].append(value)

    print("params", params)

    response = requests.get(base_url, params=params)

    if response.status_code == 200:
        response_data = response.json()
        tids = response_data["tids"]
        taxa_list = []
        for tid in tids:
            try:
                taxa = get_taxa_by_tid(int(tid)).__dict__
                taxa_list.append(taxa)
            except KeyError:
                print(f"KeyError: Taxa not found for tid {tid}")
                continue
        ret = {"data": taxa_list}
        print("ret", ret)
        return quart.Response(response=json.dumps(ret), status=200, mimetype='application/json')
    else:
        return quart.Response(response="Error", status=response.status_code)


@app.get("/.well-known/ai-plugin.json")
async def plugin_manifest():
    host = request.headers['Host']
    with open("ai-plugin.json") as f:
        text = f.read()
        # This is a trick we do to populate the PLUGIN_HOSTNAME constant in the manifest
        text = text.replace("PLUGIN_HOSTNAME", f"http://{host}")
        return quart.Response(text, mimetype="text/json")


@app.get("/openapi.yaml")
async def openapi_spec():
    host = request.headers['Host']
    with open("oregonflora.yaml") as f:
        text = f.read()
        # This is a trick we do to populate the PLUGIN_HOSTNAME constant in the OpenAPI spec
        text = text.replace("PLUGIN_HOSTNAME", f"http://{host}")
        return quart.Response(text, mimetype="text/yaml")


@app.get("/logo.png")
async def plugin_logo():
    filename = 'logo.png'
    return await quart.send_file(filename, mimetype='image/png')


def load_taxa_from_file(filename):
    with open(filename, 'r') as file:
        results = json.load(file)
        for result in results["taxa"]:
            _TAXAS[result["tid"]] = Taxa(**result)


def main():
    filename = "taxa_data.json"
    global _TAXAS

    if os.path.exists(filename):
        load_taxa_from_file(filename)
        print("Loaded taxa data from file", len(_TAXAS))
    else:
        response = requests.get(f"{BASE_URL}garden/rpc/api.php?clid=54&pid=3")
        if response.status_code == 200:
            with open(filename, 'w') as file:
                file.write(response.text)
            load_taxa_from_file(filename)
            print("Loaded taxa data from API and saved to file", len(_TAXAS))
        else:
            print("Failed to load taxa data from API")

    app.run(debug=True, host="0.0.0.0", port=5002)


if __name__ == "__main__":
    main()
