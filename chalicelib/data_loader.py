import requests
import logging
import boto3
from retry import retry
import typing
from requests_futures.sessions import FuturesSession
from concurrent.futures import as_completed

logger = logging.getLogger()
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
ch.setFormatter(formatter)
logger.addHandler(ch)

riot_api_version = "v1"


class UrlMaker(object):
    # This class responsibility is to make URLs, so that the requesting/processing
    # part is separated from here. That allows for instance that if a version of the API
    # changes, this is the only part where we would need to do modifications.

    @staticmethod
    def group_region_tag(region: str) -> str:
        europe = ["EUNE", "EUW", "TR", "RU"]
        asia = ["KR", "JP"]
        if any(group_tag in region.upper() for group_tag in asia):
            return "asia"
        elif any(group_tag in region.upper() for group_tag in europe):
            return "europe"
        else:
            return "america"

    @staticmethod
    def summoner_id(summoner_name: str, region: str) -> str:
        request_url = f"https://{region}.api.riotgames.com/tft/summoner/{riot_api_version}/summoners/by-name/"
        request_url += f"{summoner_name}"
        return request_url

    @staticmethod
    def summoner_puuid(summoner_name: str, region:str ):
        request_url = f"https://{region}.api.riotgames.com/tft/summoner/{riot_api_version}/summoners/by-name/"
        request_url += f"{summoner_name}"
        return request_url

    @staticmethod
    def summoner_entries(summoner_id: str, region: str):
        request_url = f"https://{region}.api.riotgames.com/tft/league/{riot_api_version}/entries/by-summoner/"
        request_url += f"{summoner_id}"
        return request_url

    @staticmethod
    def summoner_dto(summoner_id: str, region: str):
        request_url = f"https://{region}.api.riotgames.com/tft/summoner/{riot_api_version}/summoners/"
        request_url += f"{summoner_id}"
        return request_url

    @classmethod
    def summoner_match_ids(cls, summoner_puuid: str, region: str) -> str:
        region_tag = cls.group_region_tag(region=region)
        request_url = f"https://{region_tag}.api.riotgames.com/tft/match/{riot_api_version}/matches/by-puuid/"
        request_url += f"{summoner_puuid}/ids"
        return request_url

    @classmethod
    def match_info(cls, match_id: str, region):
        region_tag = cls.group_region_tag(region=region)
        request_url = f"https://{region_tag}.api.riotgames.com/tft/match/{riot_api_version}/matches/"
        request_url += f"{match_id}"
        return request_url

    @staticmethod
    def challenger_list(region: str):
        request_url = f'https://{region}.api.riotgames.com/tft/league/{riot_api_version}/challenger'
        return request_url


class UrlRequester(object):

    @staticmethod
    @retry(exceptions=requests.exceptions.SSLError, logger=logger,
           delay=0.250, jitter=1, max_delay=16, tries=64)
    @retry(exceptions=requests.exceptions.HTTPError, logger=logger,
           delay=5, backoff=2, max_delay=320, tries=8)
    def get_json_reply(url: str, **params):
        session = requests.Session()
        response = session.request('GET', url=url, params=params)
        try:
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            raise e
        except requests.exceptions.SSLError as e:
            raise e
        except Exception as e:
            raise e

    @staticmethod
    def future_response_hook(resp, *args, **kwargs):
        # parse the json storing the result on the response object
        resp.data = resp.json()


class DataLoader:

    def __init__(self, key: str):
        self.key = key

    def get_summoner_matches(self, summoner_name: str, region: str, count: int = 20):
        puuid_request_url = UrlMaker.summoner_puuid(region=region, summoner_name=summoner_name)
        summoner_data = UrlRequester.get_json_reply(puuid_request_url, **{'api_key': self.key})
        summoner_puuid = summoner_data["puuid"]

        match_ids_request_url = UrlMaker.summoner_match_ids(summoner_puuid=summoner_puuid,
                                                            region=region)
        summoner_match_ids = UrlRequester.get_json_reply(url=match_ids_request_url,
                                                         **{'api_key': self.key, 'count': count})

        match_infos = self.get_matches_future(match_ids=summoner_match_ids, region=region)
        return match_infos

    def get_matches_future(self, match_ids: typing.List[str], region: str):
        session = FuturesSession(max_workers=4)
        urls = [UrlMaker.match_info(region=region, match_id=match_id) +
                f"?api_key={self.key}" for match_id in match_ids]
        match_urls = [session.get(url, hooks={'response': UrlRequester.future_response_hook}) for url in urls]
        match_infos = [future.result().data for future in as_completed(match_urls)]
        return match_infos

    def get_current_challenger_names(self, region: str):
        challenger_entries_request_url = UrlMaker.challenger_list(region=region)
        challenger_list = UrlRequester.get_json_reply(
            url=challenger_entries_request_url, **{'api_key': self.key})["entries"]
        league_points_per_challenger = {}
        for challenger in challenger_list:
            league_points_per_challenger[challenger['summonerName']] = challenger['leaguePoints']
        return league_points_per_challenger


class DataWriter(DataLoader):

    @staticmethod
    def get_column_items(resource: boto3.resource, table_name: str, column_name: str):
        table = resource.Table(table_name)
        response = table.scan()
        items = [response[column_name] for response in response['Items']]
        return items

    def update_data_challenger(self, region: str):
        resource = boto3.resource('dynamodb')
        challenger_entries_request_url = UrlMaker.challenger_list(region=region)
        new_challenger_list = UrlRequester.get_json_reply(
            url=challenger_entries_request_url, **{'api_key': self.key})["entries"]
        old_challenger_ids = set(self.get_column_items(resource=resource,
                                                       table_name='challenger_infos',
                                                       column_name='summonerId'))
        new_challenger_ids = set([challenger["summonerId"] for challenger in new_challenger_list])
        challenger_ids_to_remove = old_challenger_ids - new_challenger_ids
        client = boto3.client('dynamodb')

        for old_challenger_id in challenger_ids_to_remove:
            logger.info(f'Deleting {len(challenger_ids_to_remove)} items')
            client.delete_item(TableName="challenger_infos",
                               Key={'summonerId': {'S': old_challenger_id}})

        for challenger in new_challenger_list:
            for key, value in challenger.items():
                if isinstance(value, str):
                    key_type = "S"
                    challenger[key] = {key_type: str(value)}
                elif isinstance(value, bool):
                    key_type = "BOOL"
                    challenger[key] = {key_type: value}
                elif isinstance(value, int):
                    key_type = "N"
                    challenger[key] = {key_type: str(value)}
        for challenger in new_challenger_list:
            client.put_item(TableName='challenger_infos', Item=challenger)

