# -*- coding: utf-8; -*-
#
# This file is part of Superdesk.
#
# Copyright 2013, 2014 Sourcefabric z.u. and contributors.
#
# For the full copyright and license information, please see the
# AUTHORS and LICENSE files distributed with this source code, or
# at https://www.sourcefabric.org/superdesk/license

import logging

from superdesk.errors import IngestApiError
from superdesk.io.registry import register_feeding_service, register_feeding_service_parser
from superdesk.io.feeding_services.http_base_service import HTTPFeedingServiceBase

logger = logging.getLogger(__name__)


class ANPNewsApiFeedingService(HTTPFeedingServiceBase):
    """
    Feeding Service class which can retrieve news items using ANP News API
    """

    NAME = 'anp_news_api'
    label = 'ANP News API'
    fields = HTTPFeedingServiceBase.AUTH_FIELDS + [
        {
            'id': 'source_titles',
            'type': 'text',
            'label': 'Source titles',
            'placeholder': 'Use coma separated source titles. Example: AFN, ANP 101, Medianet BIN',
            'required': True
        }
    ]
    HTTP_TIMEOUT = 60
    HTTP_AUTH = True
    HTTP_SOURCES_URL = 'https://newsapi.anp.nl/services/sources'
    HTTP_ITEMS_URL = 'https://newsapi.anp.nl/services/sources/{source_id}/items'
    HTTP_ITEM_DETAILS_URL = 'https://newsapi.anp.nl/services/sources/{source_id}/items/{item_id}'
    HTTP_ITEM_MEDIA_LIST_URL = 'https://newsapi.anp.nl/services/sources/{source_id}/items/{item_id}/media'
    HTTP_ITEM_MEDIA_DETAILS_URL = 'https://newsapi.anp.nl/services/sources/{source_id}/items/{item_id}/media/{media_id}'
    ALLOWED_ITEM_KINDS = ('TEXTARTICLE',)
    ALLOWED_MEDIA_KINDS = ('imgMid', )
    ALLOWED_MEDIA_MIMETYPES = ('image/jpeg', )

    def get_url(self, url=None, **kwargs):
        """Do an HTTP Get on URL and validate response.

        :param string url: url to use (None to use self.HTTP_URL)
        :param **kwargs: extra parameter for requests
        :return dict: response content data
        """
        response = super().get_url(url=url, **kwargs)
        content = response.json()

        if content['hasError']:
            msg = "Error in GET: '{}'. ErrorCode: '{}'. Description: '{}'".format(
                url,
                content['data']['errorCode'],
                content['data']['description']
            )
            logger.error(msg)
            raise IngestApiError.apiGeneralError(Exception(msg), self.provider)

        return content['data']

    def _update(self, provider, update):
        """
        Fetch news items from ANP News http API

        :param provider: Ingest Provider Details.
        :type provider: dict
        :param update: Any update that is required on provider.
        :type update: dict
        :return: a list of news items which can be saved.
        """

        parser = self.get_feed_parser(provider)
        # http fetch sources
        sources = self._fetch_sources()
        parsed_items = []

        for source in sources:
            # http fetch items ids
            source['items'] = self._fetch_items(
                source_id=source['id'],
                to_item=provider.get('private', {}).get('sources', {}).get(source['id'], {}).get('last_item_id')
            )

            for item in [i for i in source['items'] if i['kind'] in self.ALLOWED_ITEM_KINDS]:
                # http fetch item detail
                item_details = self._fetch_item_details(source_id=source['id'], item_id=item['id'])

                update.setdefault('private', {}).setdefault('sources', {})[source['id']] = {
                    'title': source['title'],
                    'last_item_id': item_details['id']
                }

                # parse item
                parsed_items.append(
                    parser.parse(article=item_details, provider=provider)
                )

        return [parsed_items]

    def _fetch_sources(self):
        """
        Fetch available sources and retrieves ids for `source_titles`

        :return: a list of news sources.
        """

        sources = self.get_url(url=self.HTTP_SOURCES_URL)

        return [
            src for src in sources if src['title'].lower() in [
                title.lower().strip() for title in [
                    title_conf.lower().strip() for title_conf in self.config['source_titles'].split(',')
                ]
            ]
        ]

    def _fetch_items(self, source_id, to_item=None):
        """
        Fetch items ids for given source id
        :param source_id:
        :type provider: int
        :return: a list of items ids.
        """
        payload = {}
        if to_item:
            payload['params'] = {'toItem': to_item}
        items = self.get_url(
            url=self.HTTP_ITEMS_URL.format(source_id=source_id), **payload
        )
        items['items'].reverse()

        return items['items']

    def _fetch_item_details(self, source_id, item_id):
        """
        Fetch item's details for given source id and item id
        :param source_id:
        :type provider: int
        :param item_id:
        :type provider: int
        :return: a dict with item's details
        """

        item_details = self.get_url(
            url=self.HTTP_ITEM_DETAILS_URL.format(source_id=source_id, item_id=item_id)
        )

        if item_details.get('hasMedia'):
            media_link = self._fetch_media_link(source_id, item_id)
            if media_link:
                item_details['media_link'] = media_link

        return item_details

    def _fetch_media_link(self, source_id, item_id):
        """
        Fetch a list of all available renditions for an item and return a link to file

        :param source_id:
        :param item_id:
        :return str or None: link to the image or None
        """
        # fetch media renditions
        media_renditions = self.get_url(
            url=self.HTTP_ITEM_MEDIA_LIST_URL.format(source_id=source_id, item_id=item_id)
        )
        for rend in media_renditions:
            if rend.get('kind') in self.ALLOWED_MEDIA_KINDS and rend.get('mimeType') in self.ALLOWED_MEDIA_MIMETYPES:
                media_id = rend.get('id')
                if media_id:
                    return self.HTTP_ITEM_MEDIA_DETAILS_URL.format(
                        source_id=source_id,
                        item_id=item_id,
                        media_id=media_id
                    )
                return None


register_feeding_service(ANPNewsApiFeedingService)
register_feeding_service_parser(ANPNewsApiFeedingService.NAME, 'anp_news_api')
