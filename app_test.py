import json
import pytest
from app import app
from chalice.config import Config
from chalice.local import LocalGateway
from chalicelib import utils
from chalicelib import data_loader


@pytest.fixture
def gateway_factory():
    def create_gateway(config=None):
        if config is None:
            config = Config()
        return LocalGateway(app, config)
    return create_gateway


class TestUtils(object):
    def test_riot_key_access(self):
        utils.get_secret_api()


class TestUrlRequester(object):
    def test_summoner_puuid(self):
        key = utils.get_secret_api()
        request_url = data_loader.UrlMaker.summoner_puuid(region='euw1', summoner_name='ambatv')
        params = {'api_key': key}
        data_loader.UrlRequester.get_json_reply(request_url, **params)

    # make a test for each functions.


class TestChalice(object):

    def test_get_current_challenger_data(self, gateway_factory):
        gateway = gateway_factory()
        response = gateway.handle_request(method='GET',
                                          path='/euw1/challenger_names',
                                          headers={},
                                          body='')
        assert response['statusCode'] == 200
        assert len(json.loads(response["body"])) == 200

    def test_get_summoner_matches(self, gateway_factory):
        gateway = gateway_factory()
        response = gateway.handle_request(method='GET',
                                          path=f'/euw1/matches_by_id/ambatv',
                                          headers={},
                                          body='')
        assert response['statusCode'] == 200
        assert len(json.loads(response['body'])) == 20
