from flask import Flask, request, Response, abort
from oauthlib.oauth2 import BackendApplicationClient
from requests_oauthlib import OAuth2Session
import json
import os
import copy
import requests
import datetime
from jinja2 import Template
from sesamutils import sesam_logger
from sesamutils.flask import serve

app = Flask(__name__)

PORT = int(os.environ.get("PORT", 5001))

logger = sesam_logger("rest-transform-service")

url = os.environ["URL"]
headers = json.loads(os.environ.get("HEADERS", "{}"))
authorization = os.environ.get("AUTHORIZATION")
do_verify_ssl = os.environ.get("DO_VERIFY_SSL", "false").lower() == "true"

print(f"starting with {url}")

session_factory = None

class BasicUrlSystem():
    def __init__(self, config):
        self._config = config

    def make_session(self):
        session = requests.Session()
        session.auth = tuple(self._config.get("basic")) if self._config.get("basic") else None
        session.headers = self._config["headers"]
        session.verify = do_verify_ssl
        return session


class Oauth2System():
    def __init__(self, config):
        """init Oauth2Client with a json config"""
        self._config = config
        self._get_token()

    def _get_token(self):
        # If no token has been created yet or if the previous token has expired, fetch a new access token
        # before returning the session to the callee
        if not hasattr(self, "_token") or self._token["expires_at"] <= datetime.datetime.now().timestamp():
            oauth2_client = BackendApplicationClient(client_id=self._config["oauth2"]["client_id"])
            session = OAuth2Session(client=oauth2_client)
            logger.debug("Updating token...")
            self._token = session.fetch_token(**self._config["oauth2"])

        logger.debug("expires_at[{}] - now[{}]={} seconds remaining".format(self._token["expires_at"],datetime.datetime.now().timestamp(), self._token["expires_at"] - datetime.datetime.now().timestamp()))
        return self._token

    def make_session(self):
        token = self._get_token()
        client = BackendApplicationClient(client_id=self._config["oauth2"]["client_id"])
        session = OAuth2Session(client=client, token=token)
        session.headers = self._config["headers"]
        session.verify = do_verify_ssl
        return session

if authorization:
    authorization = json.loads(authorization)
    if authorization.get("type", "") == "oauth2":
        session_factory = Oauth2System({"oauth2": authorization.get("oauth2"), "headers": headers})
    else:
        session_factory = BasicUrlSystem({"basic": authorization.get("basic"), "headers": headers})
else:
        session_factory = BasicUrlSystem({"headers": headers})

logger.info('doing stuff')

@app.route("/workorders", methods=["POST"])
def receiver():

    def do_request(session: requests.Session, method: str, entity: dict):
        if method == 'update':
            resp = session.put(f'{url}/ElWinAvtaler/api/workorders', json=entity)
        elif method == 'get':
            resp = session.get(f'{url}/ElWinAvtaler/api/workorders?externalIds={entity["ExternalId"]}')
        elif method == 'create':
            resp = session.post(f'{url}/ElWinAvtaler/api/workorders', json=entity)
        returnval = resp.content.decode('UTF-8')
        logger.debug(f'Method {method} for entity {entity["_id"]} gave response {returnval}')
        print(f'Method {method} for entity {entity["_id"]} gave response {returnval}')
        return returnval

    def generate(entities):
        with session_factory.make_session() as s:
            for entity in entities:
                # If entity has Id then we just update
                if entity.get('Id', None) is not None:
                    returnval = do_request(s, 'update', entity)
                else: # Try to find entity based on externalId
                    #If response is not JSON then we need to create the entity
                    try:
                        response_entity = json.loads(do_request(s, 'get', entity))
                    except json.JSONDecodeError:
                        logger.debug(f'Could not GET entity {entity["ExternalId"]}')
                        print(f'Could not GET entity {entity["ExternalId"]}')
                        response_entity = {}

                    # If we find the Id then we update, else we create.
                    if response_entity.get('Id', None) is not None:
                        entity['Id'] = response_entity['Id']
                        returnval = do_request(s, 'update', entity)
                    else:
                        if 'Id' in entity:
                            del entity['Id']
                        returnval = do_request(s, 'create', entity)

        return returnval




    # get entities from request
    entities = request.get_json()
    response_data = generate(entities)
    logger.debug('i did something')
    print('i did something')
    return Response(response=response_data)


if __name__ == "__main__":
    serve(app, port=PORT)
