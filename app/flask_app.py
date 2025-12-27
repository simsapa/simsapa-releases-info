#!/usr/bin/env python3

from socket import gethostname
from typing import Optional
from pathlib import Path
from datetime import datetime
import os, json, base64

import tomlkit
from tomlkit import TOMLDocument
from dotenv import load_dotenv

from flask import Flask, abort, jsonify, request, send_file
from flask.wrappers import Response
from flask_login import LoginManager

app = Flask(__name__)
# app.config["DEBUG"] = True

IS_PYTHONANYWHERE = ('console' in gethostname())

# .env file is in project root
# load_dotenv(Path(__file__).parent.joinpath('.env'))
load_dotenv("/home/simsapa/simsapa-releases-info/.env")

s = os.getenv('SECRET_API_KEY')
if s is not None and s != '':
    SECRET_API_KEY = s
else:
    SECRET_API_KEY = None

ASSETS_DIR = Path(__file__).parent.joinpath("assets")
RELEASES_TOML_MAIN_PATH = ASSETS_DIR.joinpath("releases.toml")
RELEASES_TOML_DEV_PATH = ASSETS_DIR.joinpath("releases-dev.toml")
RELEASES_TOML_SIMSAPA_NG_PATH = ASSETS_DIR.joinpath("releases-simsapa-ng.toml")
STATS_TSV_PATH = ASSETS_DIR.joinpath("stats.tsv")

if not STATS_TSV_PATH.exists():
    STATS_TSV_PATH.touch()

login_manager = LoginManager()
login_manager.init_app(app)

@app.route('/', methods = ['GET', 'POST'])
def index():
    return "☸", 200

@app.route('/releases', methods = ['GET', 'POST'])
def releases():
    toml_file_path = RELEASES_TOML_MAIN_PATH

    if request.method == 'GET':
        #
        # Simsapa sends a POST request. GET request is probably during testing.
        #
        channel = request.args.get('channel', default='main')
        if channel == 'development':
            toml_file_path = RELEASES_TOML_DEV_PATH
        elif channel == 'simsapa-ng':
            toml_file_path = RELEASES_TOML_SIMSAPA_NG_PATH

    elif request.method == 'POST' \
         and request.content_type == 'application/json':

        try:
            params: dict = request.get_json(cache=False)
        except Exception as e:
            return Response(str(e), 400)

        val = params.get('no_stats', False)

        if isinstance(val, bool):
            no_stats = val
        elif isinstance(val, str):
            no_stats = (val.lower() == "true")
        else:
            no_stats = False

        channel = params.get('channel', 'main')
        if channel == 'development':
            toml_file_path = RELEASES_TOML_DEV_PATH
        elif channel == 'simsapa-ng':
            toml_file_path = RELEASES_TOML_SIMSAPA_NG_PATH

        if not no_stats:
            # On PythonAnywhere, request.remote_addr is the proxy's address.
            # The real remote IP is the first item of the "X-Forwarded-For" header.
            remote_addr = None
            if request.headers.getlist("X-Forwarded-For"):
                ips = request.headers.getlist("X-Forwarded-For")
                if len(ips) > 0:
                    remote_addr = ips[0]

            # Or try the "X-Real-IP" header.
            if remote_addr is None:
                remote_addr = request.headers.get("X-Real-IP")

            if remote_addr is None:
                remote_addr = request.remote_addr

            with open(STATS_TSV_PATH, mode = 'a', encoding = 'utf-8') as f:
                # Seconds precision is 19 chars (2023-09-16 05:07:56), which leaves a wider gap when tabstops are displayed in the terminal.
                data = "%s\t%s\t%s\n" % (datetime.utcnow().isoformat(sep=' ', timespec='seconds'), remote_addr, json.dumps(params))
                f.write(data)

    else:
        return Response("Expected POST request parameters as JSON data", 400)

    return jsonify(parse_toml(toml_file_path)), 200

@login_manager.request_loader
@app.route('/stats', methods = ['GET'])
def export():
    # Must use https:// except when testing locally.
    # Otherwise the Basic Auth creds are sent in clear text.
    if IS_PYTHONANYWHERE and not request.is_secure:
        return abort(403)

    if SECRET_API_KEY is None:
        return abort(403)

    # login using Basic Auth
    api_key = request.headers.get('Authorization')
    if api_key:
        api_key = api_key.replace('Basic ', '', 1)
        try:
            api_key = base64.b64decode(api_key).decode('utf-8')
        except TypeError:
            pass

        if api_key != SECRET_API_KEY:
            return abort(403)

        return send_file(STATS_TSV_PATH)

    else:
        return abort(403)

@app.errorhandler(400)
def resp_bad_request(e):
    msg = f"Bad Request: {e}"
    return msg, 400

@app.errorhandler(404)
def resp_not_found(e):
    msg = f"Not Found: {e}"
    return msg, 404

@app.errorhandler(403)
def resp_forbidden(__e__):
    return "Hey!", 403

def parse_toml(path: Path) -> Optional[TOMLDocument]:
    with open(path) as f:
        s = f.read()

    t = None
    try:
        t = tomlkit.parse(s)
    except Exception as e:
        msg = f"Can't parse TOML: {path}\n\n{e}"
        raise Exception(msg)

    return t

if __name__ == '__main__':
    if not IS_PYTHONANYWHERE:
        app.run(host='127.0.0.1', port=5000, debug=True)
