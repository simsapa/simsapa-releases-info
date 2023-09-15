#!/usr/bin/env python3

from socket import gethostname
from typing import Optional, Dict
from pathlib import Path
from datetime import datetime
import os, json, base64

import tomlkit
from tomlkit import TOMLDocument
from dotenv import load_dotenv

from flask import Flask, abort, jsonify, request
from flask.wrappers import Response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from sqlalchemy.orm import Mapped, declarative_base, mapped_column
from sqlalchemy import Integer, String, DateTime

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

if IS_PYTHONANYWHERE:
    d = dict()
    for key in ['MYSQL_HOST', 'MYSQL_DB_NAME', 'MYSQL_USER', 'MYSQL_PASS']:
        s = os.getenv(key)
        d[key] = s

    databasename = "%s$%s" % (d['MYSQL_USER'], d['MYSQL_DB_NAME'])

    SQLALCHEMY_DATABASE_URI = "mysql+mysqlconnector://{username}:{password}@{hostname}/{databasename}".format(
        username = d['MYSQL_USER'],
        password = d['MYSQL_PASS'],
        hostname = d['MYSQL_HOST'],
        databasename = databasename,
    )

else:
    SQLALCHEMY_DATABASE_URI = "sqlite:///appdata.sqlite"

app.config["SQLALCHEMY_DATABASE_URI"] = SQLALCHEMY_DATABASE_URI
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_recycle' : 280}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

Base = declarative_base()

db = SQLAlchemy(app, model_class=Base)

class Stat(db.Model):
    __tablename__ = "stats"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    params_json: Mapped[str] = mapped_column(String(500), unique=False, nullable=False)
    remote_addr: Mapped[Optional[str]] = mapped_column(String(100), unique=False, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    def __init__(self, **kwargs):
        super(Stat, self).__init__(**kwargs)

ASSETS_DIR = Path(__file__).parent.joinpath("assets")
RELEASES_TOML_MAIN_PATH = ASSETS_DIR.joinpath("releases.toml")
RELEASES_TOML_DEV_PATH = ASSETS_DIR.joinpath("releases-dev.toml")
STATS_CSV_PATH = ASSETS_DIR.joinpath("stats.csv")

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

    elif request.method == 'POST' \
         and request.content_type == 'application/json':

        try:
            params: dict = request.get_json(cache=False)
        except Exception as e:
            return Response(str(e), 400)

        no_stats = params.get('no_stats', False)

        if params.get('channel', 'main') == 'development':
            toml_file_path = RELEASES_TOML_DEV_PATH

        if not no_stats:
            with app.app_context():
                item = Stat(
                    params_json = json.dumps(params),
                    remote_addr = str(request.remote_addr),
                )
                db.session.add(item)
                db.session.commit()

    else:
        return Response("Expected POST request parameters as JSON data", 400)

    return jsonify(parse_toml(toml_file_path)), 200

@login_manager.request_loader
@app.route('/export', methods = ['GET'])
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

        with app.app_context():

            def _stat_to_row(x: Stat) -> Dict[str, str]:
                row = dict()
                row['id'] = str(x.id)
                row['remote_addr'] = str(x.remote_addr)
                row['created_at'] = str(x.created_at)
                row['params_json'] = str(x.params_json)

                return row

            stats = Stat.query.all()
            rows = [_stat_to_row(x) for x in stats]

            return jsonify(rows), 200

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
    with app.app_context():
        db.create_all()

    if not IS_PYTHONANYWHERE:
        app.run(host='127.0.0.1', port=5000, debug=True)
