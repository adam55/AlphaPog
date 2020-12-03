from chalice import Chalice, Rate
from chalicelib.data_loader import DataLoader, DataWriter
import logging
from chalicelib.utils import get_secret_api

app = Chalice(app_name='alpha_tft_v1')


@app.route('/{region}/challenger_names')
def get_current_challenger_data(region):
    key = get_secret_api()
    logging.info(key)
    data_loader = DataLoader(key=key)
    return data_loader.get_current_challenger_names(region=region)


@app.schedule(Rate(1, unit=Rate.MINUTES))
def update_euw_challenger_data(event):
    key = get_secret_api()
    data_writer = DataWriter(key=key)
    data_writer.update_data_challenger(region='euw1')


@app.route('/{region}/matches_by_id/{user_name}')
def get_matches_info(region, user_name):
    key = get_secret_api()
    data_loader = DataLoader(key=key)
    match_infos = data_loader.get_summoner_matches(summoner_name=user_name, region=region)
    return match_infos

