import json
import os
import random
from dataclasses import dataclass
import csv
from io import StringIO

import quart
import quart_cors
import requests
from quart import request

# Note: Setting CORS to allow chat.openapi.com is required for ChatGPT to access your plugin
app = quart_cors.cors(quart.Quart(__name__), allow_origin="https://chat.openai.com")

_TAXAS = {}
BASE_URL = "https://oregonflora.org/"
BASE_PARAMS = {"clid": 54, "pid": 3}  # unknown magic values


@dataclass
class Taxa:
    tid: int
    family: str
    sciname: str
    parenttid: int
    author: str
    imgid: int
    vernacular: list[str]
    image: str
    link: str = ""


def parse_taxa(**kwargs) -> Taxa:
    kwargs["vernacular"] = ", ".join(kwargs["vernacular"]["names"])
    t = Taxa(**kwargs)
    t.image = BASE_URL + t.image
    t.link = BASE_URL + "taxa/garden.php?taxon=" + str(t.tid)
    return t


def get_taxa_by_tid(tid: int) -> Taxa:
    return _TAXAS[tid]


def handle_range_param(value: str, param_number: int, params: dict) -> None:
    # range parameters are encoded in a special way, using a `range` param with values encoding min and max. examples:
    # height: /garden/rpc/api.php?clid=54&pid=3&range%5B%5D=140-n-33&range%5B%5D=140-x-51
    # width:  /garden/rpc/api.php?clid=54&pid=3&range%5B%5D=738-n-36&range%5B%5D=738-x-81
    if 'range[]' not in params:
        params['range[]'] = []
    mn, mx = value.split("-", 2)
    params['range[]'].append(f"{param_number}-n-{mn}")
    params['range[]'].append(f"{param_number}-x-{mx}")


@app.get("/detail/<int:tid>")
async def detail(tid: int):
    url = f"{BASE_URL}taxa/rpc/api.php?taxon={tid}"
    resp = requests.get(url)
    response = resp.json()
    response.pop("imagesBasis")  # this part of the response is huge
    response.pop("spp")
    if resp.status_code == 200:
        return quart.Response(response=json.dumps(response), status=200, mimetype='application/json')
    else:
        return quart.Response(response="Error", status=resp.status_code)


@app.post("/search")
async def search():
    req = await request.get_json(force=True)
    base_url = BASE_URL + "garden/rpc/api.php"
    params = {**BASE_PARAMS}

    for key, value in req.items():
        if key == 'height':
            handle_range_param(value, 140, params)
            continue
        if key == 'width':
            handle_range_param(value, 738, params)
            continue
        if 'attr[]' not in params:
            params['attr[]'] = []
        params['attr[]'].append(value)

    response = requests.get(base_url, params=params)

    if response.status_code == 200:
        response_data = response.json()
        # take a random set of 20
        sample_size = min(20, len(response_data["tids"]))
        tids = random.sample(response_data["tids"], sample_size)
        taxa_list = []
        for tid in tids:
            try:
                taxa = get_taxa_by_tid(int(tid)).__dict__
                taxa_list.append(taxa)
            except KeyError:
                continue

        # use CSV as a denser format than JSON
        csvfile = StringIO()
        fieldnames = taxa_list[0].keys()
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for taxa in taxa_list:
            writer.writerow(taxa)
        csv_data = csvfile.getvalue()

        return quart.Response(response=csv_data, status=200, mimetype='text/csv')
    else:
        return quart.Response(response="Error", status=response.status_code)



@app.get("/.well-known/ai-plugin.json")
async def plugin_manifest():
    with open("ai-plugin.json") as f:
        text = f.read()
        text = text.replace("PLUGIN_HOSTNAME", f"{request.scheme}://{request.headers['Host']}")
        return quart.Response(text, mimetype="text/json")


@app.get("/openapi.yaml")
async def openapi_spec():
    with open("oregonflora.yaml") as f:
        text = f.read()
        text = text.replace("PLUGIN_HOSTNAME", f"{request.scheme}://{request.headers['Host']}")
        return quart.Response(text, mimetype="text/yaml")


@app.get("/logo.png")
async def plugin_logo():
    filename = 'logo.png'
    return await quart.send_file(filename, mimetype='image/png')


def load_taxa_from_file(filename):
    with open(filename, 'r') as file:
        results = json.load(file)
        for result in results["taxa"]:
            _TAXAS[result["tid"]] = parse_taxa(**result)


def main():
    filename = "taxa_data.json"
    global _TAXAS

    # at boot time, load in the entire db of plant data (this is how the web frontend works). cache it locally to make
    # iterating locally easier.

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
