"""
AmazonSimpleProductAPI
"""
# coding=utf-8
# !/usr/bin/python
#
# Copyright (C) 2012 Yoav Aviram.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from __future__ import absolute_import, division, print_function, unicode_literals

import os

from lxml import etree, objectify
from lxml.etree import Element

try:
    from .bottlenose import *
except:
    execfile(str('bottlenose.py'))


# try:
#     # noinspection PyUnresolvedReferences
#     from typing import Any, Iterable, Optional, Dict, List, Tuple, unicode, Set, Text
# except ImportError:
#     pass

class AmazonException(Exception):
    """Base Class for BottlenoseAmazon Api Exceptions.
    """

    def __init__(self, code=None, msg=None):
        self.code = code
        self.msg = msg


class CartException(AmazonException):
    """Cart related Exception
    """

    def __init__(self, code=None, msg=None):
        super(CartException, self).__init__(code, msg)


class CartInfoMismatchException(CartException):
    """HMAC, CartId and AssociateTag did not match
    """

    def __init__(self, code=None, msg=None):
        super(CartInfoMismatchException, self).__init__(code, msg)


class AsinNotFoundException(AmazonException):
    """ASIN Not Found Exception.
    """

    def __init__(self, code=None, msg=None):
        super(AsinNotFoundException, self).__init__(code, msg)


class LookupException(AmazonException):
    """Lookup Exception.
    """

    def __init__(self, code, msg):
        super(LookupException, self).__init__(code, msg)


class SearchException(AmazonException):
    """Search Exception.
    """

    def __init__(self, code, msg):
        super(SearchException, self).__init__(code, msg)


class NoMorePagesException(SearchException):
    """No More Pages Exception.
    """

    def __init__(self, code=None, msg=None):
        super(NoMorePagesException, self).__init__(code, msg)


class RequestThrottledException(AmazonException):
    """Exception for when BottlenoseAmazon has throttled a request, per:
    http://docs.aws.amazon.com/AWSECommerceService/latest/DG/ErrorNumbers.html
    """

    def __init__(self, code=None, msg=None):
        super(RequestThrottledException, self).__init__(code, msg)


class SimilartyLookupException(AmazonException):
    """Similarty Lookup Exception.
    """

    def __init__(self, code=None, msg=None):
        super(SimilartyLookupException, self).__init__(code, msg)


class BrowseNodeLookupException(AmazonException):
    """Browse Node Lookup Exception.
    """

    def __init__(self, code=None, msg=None):
        super(BrowseNodeLookupException, self).__init__(code, msg)


class AmazonAPI(object):
    """
    Used to call Amazon API
    """
    # https://kdp.amazon.com/help?topicId=A1CT8LK6UW2FXJ
    AMAZON_DOMAINS = {u'CA': u'ca', u'DE': u'de', u'ES': u'es', u'FR': u'fr', u'IN': u'in', u'IT': u'it',
                      u'JP': u'co.jp', u'UK': u'co.uk', u'US': u'com', u'CN': u'cn'}

    AMAZON_ASSOCIATES_BASE_URL = u'http://www.amazon.{domain}/dp/'

    # noinspection PyTypeChecker
    def __init__(self, aws_key=os.environ.get(u'AWS_ACCESS_KEY_ID'),
                 aws_secret=os.environ.get(u'AWS_SECRET_ACCESS_KEY'),
                 aws_associate_tag=os.environ.get(u'AWS_ASSOCIATE_TAG'), MaxQPS=None, Timeout=None, CacheReader=None,
                 CacheWriter=None,
                 **kwargs):
        # type: (unicode, unicode, unicode, float, int, object, object, dict) -> AmazonAPI
        """Initialize an BottlenoseAmazon API Proxy.

        kwargs values are passed directly to Bottlenose. Check the Bottlenose
        API for valid values (some are provided below).

        :type kwargs: Dict[Any]
        :param aws_key:
            A string representing an AWS authentication key.
        :param aws_secret:
            A string representing an AWS authentication secret.
        :param aws_associate_tag:
            A string representing an AWS associate tag.

        Important Bottlenose arguments:
        :param MaxQPS:
            Optional maximum queries per second. If we've made an API call
            on this object more recently that 1/MaxQPS, we'll wait
            before making the call. Useful for making batches of queries.
            You generally want to set this a little lower than the
            max (so 0.9, not 1.0).
            BottlenoseAmazon limits the number of calls per hour, so for long running
            tasks this should be set to 0.9 to ensure you don't hit the
            maximum.
            Defaults to None (unlimited).
        :param Timeout:
            Optional timeout for queries.
            Defaults to None.
        :param CacheReader:
            Called before attempting to make an API call.
            A function that takes a single argument, the URL that
            would be passed to the API, minus auth information,
            and returns a cached version of the (unparsed) response,
            or None.
            Defaults to None.
        :param CacheWriter:
            Called after a successful API call. A function that
            takes two arguments, the same URL passed to
            CacheReader, and the (unparsed) API response.
            Defaults to None.
        """
        kwargs.update(
            {u'MaxQPS': MaxQPS, u'Timeout': Timeout, u'CacheReader': CacheReader, u'CacheWriter': CacheWriter})
        self.api = BottlenoseAmazon(AWSAccessKeyId=aws_key, AWSSecretAccessKey=aws_secret,
                                    AssociateTag=aws_associate_tag, **kwargs)

    def item_lookup(self, ItemId, IdType=u'ASIN', ResponseGroup=u'Large', **kwargs):
        # type: (unicode, unicode, unicode, dict) -> list(AmazonProduct)
        """Lookup an BottlenoseAmazon Product.
        :param ItemId: A single ItemId
        :param IdType: One of ASIN, SKU, EAN, UPC or ISBN
        :param ResponseGroup: Response group
        :return:List[AmazonProduct]:List of Amazon Products
        """
        kwargs.update({u'ItemId': unicode(ItemId), u'IdType': unicode(IdType), u'ResponseGroup': unicode(ResponseGroup),
                       u'Operation': u'ItemLookup'})
        response = self.api.call_api(**kwargs)
        root = objectify.fromstring(response)
        if root.Items.Request.IsValid == u'False':
            code = root.Items.Request.Errors.Error.Code
            msg = root.Items.Request.Errors.Error.Message
            raise LookupException(code, msg)
        if not hasattr(root.Items, u'Item'):
            raise AsinNotFoundException(code=20, msg=u'ASIN(s) not found: \'{0}\''.format(
                etree.tostring(root, pretty_print=True)))
        return [AmazonProduct(item) for item in root.Items.Item]

    def item_search(self, ResponseGroup=u'Large', **kwargs):
        # type: (unicode, dict) -> list[AmazonProduct]
        """Seach

        :param ResponseGroup:
        :param kwargs:
        :return:
        """
        kwargs.update({u'Operation': u'ItemSearch', u'ResponseGroup': unicode(ResponseGroup)})
        response = self.api.call_api(**kwargs)
        root = objectify.fromstring(response)
        if root.Items.Request.IsValid == u'False':
            code = root.Items.Request.Errors.Error.Code
            msg = root.Items.Request.Errors.Error.Message
            raise SearchException(code, msg)
        if not hasattr(root.Items, u'Item'):
            raise SearchException(code=1, msg=u'No item found in tree')
        return [AmazonProduct(item) for item in root.Items.Item]


class _LXMLWrapper(object):
    def __init__(self, parsed_response):
        self.parsed_response = parsed_response

    def to_string(self):
        """Convert Item XML to string.

        :return:
            A string representation of the Item xml.
        """
        return etree.tostring(self.parsed_response, pretty_print=True)

    def _safe_get_element(self, path, root=None):
        """Safe Get Element.

        Get a child element of root (multiple levels deep) failing silently
        if any descendant does not exist.

        :param root:
            Lxml element.
        :param path:
            String path (i.e. u'Items.Item.Offers.Offer').
        :return:
            Element or None.
        """
        elements = path.split(u'.')
        parent = root if root is not None else self.parsed_response
        for element in elements[:-1]:
            parent = getattr(parent, element, None)
            if parent is None:
                return None
        return getattr(parent, elements[-1], None)

    def _safe_get_element_text(self, path, root=None):
        # type: (Element, [unicode or None]) -> unicode or None
        """Safe get element text.

        Get element as string or None,
        :rtype: Text or None
        :param root: Lxml element.
        :param path: String path (i.e. u'Items.Item.Offers.Offer').
        :return: unicode or None
        """
        element = self._safe_get_element(path, root)
        if element is not None:
            return element.text
        else:
            return None

    def _safe_get_element_date(self, path, root=None):
        """Safe get elemnent date.

        Get element as datetime.date or None,
        :param root:
            Lxml element.
        :param path:
            String path (i.e. u'Items.Item.Offers.Offer').
        :return:
            datetime.date or None.
        """
        value = self._safe_get_element_text(path=path, root=root)
        if value is not None:
            try:
                from datetime import datetime
                value = datetime.strptime(value, u'%Y-%m-%d')
                if value:
                    value = value.date()
            except ValueError:
                value = None

        return value


class _AmazonSearch(object):
    """ BottlenoseAmazon Search.

    A class providing an iterable over amazon search results.
    """

    def __init__(self, api, **kwargs):
        # type: (AmazonAPI, dict) -> None
        """Initialise

        Initialise a search

        :param api:
            An instance of :class:`~.bottlenose.BottlenoseAmazon`.
        :param aws_associate_tag:
            An string representing an BottlenoseAmazon Associates tag.
        """
        self.kwargs = kwargs
        self.current_page = 0
        self.is_last_page = False
        self.api = api

    def __iter__(self):
        # type: () -> AmazonProduct
        """Iterate.

        A generator which iterate over all paginated results
        returning :class:`~.AmazonProduct` for each item.

        :return:
            Yields a :class:`~.AmazonProduct` for each result item.
        """
        for page in self.iterate_pages():
            for item in getattr(page.Items, u'Item', []):
                yield AmazonProduct(item=item)

    def iterate_pages(self):
        """Iterate Pages.

        A generator which iterates over all pages.
        Keep in mind that BottlenoseAmazon limits the number of pages it makes available.

        :return:
            Yields lxml root elements.
        """
        try:
            while not self.is_last_page:
                self.current_page += 1
                yield self._query(ItemPage=self.current_page, **self.kwargs)
        except NoMorePagesException:
            pass

    def _query(self, ResponseGroup=u'Large', **kwargs):
        """Query.

        Query BottlenoseAmazon search and check for errors.

        :return:
            An lxml root element.
        """
        response = self.api.item_search(ResponseGroup=ResponseGroup, **kwargs)
        root = objectify.fromstring(response)
        if hasattr(root.Items.Request, u'Errors') and not hasattr(root.Items, u'Item'):
            code = root.Items.Request.Errors.Error.Code
            msg = root.Items.Request.Errors.Error.Message
            if code == u'AWS.ParameterOutOfRange':
                raise NoMorePagesException(code, msg)
            elif code == u'HTTP Error 503':
                raise RequestThrottledException(code, msg)
            else:
                raise SearchException(code, msg)
        if hasattr(root.Items, u'TotalPages'):
            if root.Items.TotalPages == self.current_page:
                self.is_last_page = True
        return root


class _AmazonBrowseNode(_LXMLWrapper):
    @property
    def id(self):
        """Browse Node ID.

        A positive integer that uniquely identifies a parent product category.

        :return:
            ID (integer)
        """
        if hasattr(self.parsed_response, u'BrowseNodeId'):
            return int(self.parsed_response[u'BrowseNodeId'])
        return None

    @property
    def name(self):
        """Browse Node Name.

        :return:
            Name (string)
        """
        return getattr(self.parsed_response, u'Name', None)

    @property
    def is_category_root(self):
        """Boolean value that specifies if the browse node is at the top of
        the browse node tree.
        """
        return getattr(self.parsed_response, u'IsCategoryRoot', False)

    @property
    def ancestor(self):
        """This browse node's immediate ancestor in the browse node tree.

        :return:
            The ancestor as an :class:`~._AmazonBrowseNode`, or None.
        """
        ancestors = getattr(self.parsed_response, u'Ancestors', None)
        if hasattr(ancestors, u'BrowseNode'):
            return _AmazonBrowseNode(ancestors[u'BrowseNode'])
        return None

    @property
    def ancestors(self):
        """A list of this browse node's ancestors in the browse node tree.

        :return:
            List of :class:`~._AmazonBrowseNode` objects.
        """
        ancestors = []
        node = self.ancestor
        while node is not None:
            ancestors.append(node)
            node = node.ancestor
        return ancestors

    @property
    def children(self):
        """This browse node's children in the browse node tree.

    :return:
    A list of this browse node's children in the browse node tree.
    """
        children = []
        child_nodes = getattr(self.parsed_response, u'Children')
        for child in getattr(child_nodes, u'BrowseNode', []):
            children.append(_AmazonBrowseNode(child))
        return children


class AmazonProduct(_LXMLWrapper):
    """A wrapper class for an BottlenoseAmazon product.
    """

    # noinspection PyUnusedLocal
    def __init__(self, item):
        super(AmazonProduct, self).__init__(item)

    def __str__(self):
        """Return redable representation.

        Uses the item's title.
        """
        return self.title

    def __unicode__(self):
        """Return redable representation.

        Uses the item's title.
        """
        return self.title

    # @property
    # def price_and_currency(self):
    #     # type: () -> Tuple[Optional[float],Optional[unicode]]
    #     """Get Offer Price and Currency.
    #
    #     Return price according to the following process:
    #
    #     * If product has a sale return Sales Price, otherwise,
    #     * Return Price, otherwise,
    #     * Return lowest offer price, otherwise,
    #     * Return None.
    #
    #     :return:
    #         A tuple containing:
    #
    #             1. Decimal representation of price.
    #             2. ISO Currency code (string).
    #     """
    #     price = self._safe_get_element_text(
    #         u'Offers.Offer.OfferListing.SalePrice.Amount')
    #     if price:
    #         currency = self._safe_get_element_text(
    #             u'Offers.Offer.OfferListing.SalePrice.CurrencyCode')
    #     else:
    #         price = self._safe_get_element_text(
    #             u'Offers.Offer.OfferListing.Price.Amount')
    #         if price:
    #             currency = self._safe_get_element_text(
    #                 u'Offers.Offer.OfferListing.Price.CurrencyCode')
    #         else:
    #             price = self._safe_get_element_text(
    #                 u'OfferSummary.LowestNewPrice.Amount')
    #             currency = self._safe_get_element_text(
    #                 u'OfferSummary.LowestNewPrice.CurrencyCode')
    #     if price:
    #         dprice = Decimal(
    #             price) / 100 if u'JP' not in self.region else Decimal(price)
    #         return dprice, currency
    #     else:
    #         return None, None

    @property
    def offer_id(self):
        """Offer ID

        :return:
            Offer ID (string).
        """
        return self._safe_get_element(u'Offers.Offer.OfferListing.OfferListingId')

    @property
    def asin(self):
        """ASIN (BottlenoseAmazon ID)

        :return:
            ASIN (string).
        """
        return self._safe_get_element_text(u'ASIN')

    @property
    def sales_rank(self):
        """Sales Rank

        :return:
            Sales Rank (integer).
        """
        return self._safe_get_element_text(u'SalesRank')

    # @property
    # def offer_url(self):
    #     """Offer URL
    #
    #     :return:
    #         Offer URL (string).
    #     """
    #     return "{0}{1}/?tag={2}".format(
    #         AmazonAPI.AMAZON_ASSOCIATES_BASE_URL.format(domain=AmazonAPI.AMAZON_DOMAINS[self.region]),
    #         self.asin,
    #         self.aws_associate_tag)

    @property
    def author(self):
        """Author.
        Depricated, please use `authors`.

        :return:
            Author (string).
        """
        import warnings
        warnings.warn(u'deprecated', DeprecationWarning)
        authors = self.authors
        if len(authors):
            return authors[0]
        else:
            return None

    @property
    def authors(self):
        """Authors.

        :return:List[unicode]:Returns of list of authors
        """
        result = []
        authors = self._safe_get_element(u'ItemAttributes.Author')
        if authors is not None:
            for author in authors:
                result.append(author.text)
        return result

    @property
    def creators(self):
        """Creators.

        Creators are not the authors. These are usually editors, translators,
        narrators, etc.

        :return:
            Returns a list of creators where each is a tuple containing:

                1. The creators name (string).
                2. The creators role (string).

        """
        # return tuples of name and role
        result = []
        creators = self._safe_get_element(u'ItemAttributes.Creator')
        if creators is not None:
            for creator in creators:
                role = creator.attrib[u'Role'] if u'Role' in creator.attrib else None
                result.append((creator.text, role))
        return result

    @property
    def publisher(self):
        """Publisher.

        :return:
            Publisher (string)
        """
        return self._safe_get_element_text(u'ItemAttributes.Publisher')

    @property
    def label(self):
        """Label.

        :return:
            Label (string)
        """
        return self._safe_get_element_text(u'ItemAttributes.Label')

    @property
    def manufacturer(self):
        """Manufacturer.

        :return:
            Manufacturer (string)
        """
        return self._safe_get_element_text(u'ItemAttributes.Manufacturer')

    @property
    def brand(self):
        """Brand.

        :return:
            Brand (string)
        """
        return self._safe_get_element_text(u'ItemAttributes.Brand')

    @property
    def isbn(self):
        """ISBN.

        :return:
            ISBN (string)
        """
        return self._safe_get_element_text(u'ItemAttributes.ISBN')

    @property
    def eisbn(self):
        """EISBN (The ISBN of eBooks).

        :return:
            EISBN (string)
        """
        return self._safe_get_element_text(u'ItemAttributes.EISBN')

    @property
    def binding(self):
        """Binding.

        :return:
            Binding (string)
        """
        return self._safe_get_element_text(u'ItemAttributes.Binding')

    @property
    def pages(self):
        """Pages.

        :return:
            Pages (string)
        """
        return self._safe_get_element_text(u'ItemAttributes.NumberOfPages')

    @property
    def publication_date(self):
        """Pubdate.

        :return:
            Pubdate (datetime.date)
        """
        return self._safe_get_element_date(u'ItemAttributes.PublicationDate')

    @property
    def release_date(self):
        """Release date .

        :return:
            Release date (datetime.date)
        """
        return self._safe_get_element_date(u'ItemAttributes.ReleaseDate')

    @property
    def edition(self):
        """Edition.

        :return:
            Edition (string)
        """
        return self._safe_get_element_text(u'ItemAttributes.Edition')

    @property
    def large_image_url(self):
        """Large Image URL.

        :return:
            Large image url (string)
        """
        return self._safe_get_element_text(u'LargeImage.URL')

    @property
    def medium_image_url(self):
        """Medium Image URL.

        :return:
            Medium image url (string)
        """
        return self._safe_get_element_text(u'MediumImage.URL')

    @property
    def small_image_url(self):
        """Small Image URL.

        :return:
            Small image url (string)
        """
        return self._safe_get_element_text(u'SmallImage.URL')

    @property
    def tiny_image_url(self):
        """Tiny Image URL.

        :return:
            Tiny image url (string)
        """
        return self._safe_get_element_text(u'TinyImage.URL')

    @property
    def reviews(self):
        """Customer Reviews.

        Get a iframe URL for customer reviews.

        :return:
            A tuple of: has_reviews (bool), reviews url (string)
        """
        iframe = self._safe_get_element_text(u'CustomerReviews.IFrameURL')
        has_reviews = self._safe_get_element_text(u'CustomerReviews.HasReviews')
        if has_reviews is not None and has_reviews == u'true':
            has_reviews = True
        else:
            has_reviews = False
        return has_reviews, iframe

    @property
    def ean(self):
        # type: () -> unicode
        """EAN.

        :return:
            EAN (string)
        """
        ean = self._safe_get_element_text(u'ItemAttributes.EAN')
        if ean is None:
            ean_list = self._safe_get_element_text(u'ItemAttributes.EANList')
            if ean_list:
                ean = self._safe_get_element_text(u'EANListElement', root=ean_list[0])
        return ean

    @property
    def upc(self):
        """UPC.

        :return:
            UPC (string)
        """
        upc = self._safe_get_element_text(u'ItemAttributes.UPC')
        if upc is None:
            upc_list = self._safe_get_element_text(u'ItemAttributes.UPCList')
            if upc_list:
                upc = self._safe_get_element_text(u'UPCListElement', root=upc_list[0])
        return upc

    @property
    def color(self):
        """Color.

        :return:
            Color (string)
        """
        return self._safe_get_element_text(u'ItemAttributes.Color')

    @property
    def sku(self):
        """SKU.

        :return:
            SKU (string)
        """
        return self._safe_get_element_text(u'ItemAttributes.SKU')

    @property
    def mpn(self):
        """MPN.

        :return:
            MPN (string)
        """
        return self._safe_get_element_text(u'ItemAttributes.MPN')

    @property
    def model(self):
        """Model Name.

        :return:
            Model (string)
        """
        return self._safe_get_element_text(u'ItemAttributes.Model')

    @property
    def part_number(self):
        """Part Number.

        :return:
            Part Number (string)
        """
        return self._safe_get_element_text(u'ItemAttributes.PartNumber')

    @property
    def title(self):
        """Title.

        :return:
            Title (string)
        """
        return self._safe_get_element_text(u'ItemAttributes.Title')

    @property
    def editorial_review(self):
        """Editorial Review.

        Returns an editorial review text.

        :return:
            Editorial Review (string)
        """
        reviews = self.editorial_reviews
        if reviews:
            return reviews[0]
        return u''

    @property
    def editorial_reviews(self):
        """Editorial Review.

        Returns a list of all editorial reviews.

        :return:
            A list containing:

                Editorial Review (string)
        """
        result = []
        reviews_node = self._safe_get_element(u'EditorialReviews')

        if reviews_node is not None:
            for review_node in reviews_node.iterchildren():
                content_node = getattr(review_node, u'Content')
                if content_node is not None:
                    result.append(content_node.text)
        return result

    @property
    def languages(self):
        # type: () -> set[unicode]
        """Languages.

        Returns a set of languages in lower-case.

        :return:
            Returns a set of languages in lower-case (strings).
        """
        result = set()
        languages = self._safe_get_element(u'ItemAttributes.Languages')
        if languages is not None:
            for language in languages.iterchildren():
                text = self._safe_get_element_text(u'Name', language)
                if text:
                    result.add(text.lower())
        return result

    @property
    def features(self):
        """Features.

        Returns a list of feature descriptions.

        :return:
            Returns a list of u'ItemAttributes.Feature' elements (strings).
        """
        result = []
        features = self._safe_get_element(u'ItemAttributes.Feature')
        if features is not None:
            for feature in features:
                result.append(feature.text)
        return result

    # @property
    # def list_price(self):
    #     """List Price.
    #
    #     :return:
    #         A tuple containing:
    #
    #             1. Decimal representation of price.
    #             2. ISO Currency code (string).
    #     """
    #     price = self._safe_get_element_text(u'ItemAttributes.ListPrice.Amount')
    #     currency = self._safe_get_element_text(
    #         u'ItemAttributes.ListPrice.CurrencyCode')
    #     if price:
    #         dprice = Decimal(
    #             price) / 100 if u'JP' not in self.region else Decimal(price)
    #         return dprice, currency
    #     else:
    #         return None, None

    def get_attribute(self, name):
        """Get Attribute

        Get an attribute (child elements of u'ItemAttributes') value.

        :param name:
            Attribute name (string)
        :return:
            Attribute value (string) or None if not found.
        """
        return self._safe_get_element_text(u'ItemAttributes.{0}'.format(name))

    def get_attribute_details(self, name):
        """Get Attribute Details

        Gets XML attributes of the product attribute. These usually contain
        details about the product attributes such as units.

        :param name:
            Attribute name (string)
        :return:
            A name/value dictionary.
        """
        return self._safe_get_element(u'ItemAttributes.{0}'.format(name)).attrib

    def get_attributes(self, name_list):
        """Get Attributes

        Get a list of attributes as a name/value dictionary.

        :param name_list:
            A list of attribute names (strings).
        :return:
            A name/value dictionary (both names and values are strings).
        """
        properties = {}
        for name in name_list:
            value = self.get_attribute(name)
            if value is not None:
                properties[name] = value
        return properties

    @property
    def parent_asin(self):
        """Parent ASIN.

        Can be used to test if product has a parent.

        :return:
            Parent ASIN if product has a parent.
        """
        return self._safe_get_element(u'ParentASIN')

    # def get_parent(self):
    #     # type: () -> AmazonProduct
    #     """Get Parent.
    #
    #     Fetch parent product if it exists.
    #     Use `parent_asin` to check if a parent exist before fetching.
    #
    #     :return:
    #         An instance of :class:`~.AmazonProduct` representing the
    #         parent product.
    #     """
    #     if not self.parent:
    #         parent = self._safe_get_element(u'ParentASIN')
    #         if parent:
    #             self.parent = self.api.lookup(ItemId=parent)
    #     return self.parent

    @property
    def browse_nodes(self):
        """Browse Nodes.

        :return:
            A list of :class:`~._AmazonBrowseNode` objects.
        """
        root = self._safe_get_element(u'BrowseNodes')
        if root is None:
            return []

        return [_AmazonBrowseNode(child) for child in root.iterchildren()]

    @property
    def images(self):
        """List of images for a response.
        When using lookup with RespnoseGroup u'Images', you'll get a
        list of images. Parse them so they are returned in an easily
        used list format.

        :return:
            A list of `ObjectifiedElement` images
        """
        try:
            images = [image for image in self._safe_get_element(u'ImageSets.ImageSet')]
        except TypeError:  # No images in this ResponseGroup
            images = []
        return images

    @property
    def genre(self):
        """Movie Genre.

        :return:
            The genre of a movie.
        """
        return self._safe_get_element_text(u'ItemAttributes.Genre')

    @property
    def actors(self):
        """
        :return:List(unicode):A list of actors names.
        """
        result = []
        actors = self._safe_get_element(u'ItemAttributes.Actor') or []
        for actor in actors:
            result.append(actor.text)
        return result

    @property
    def directors(self):
        """Movie Directors.

        :return:
            A list of directors for a movie.
        """
        result = []
        directors = self._safe_get_element(u'ItemAttributes.Director') or []
        for director in directors:
            result.append(director.text)
        return result

    @property
    def is_adult(self):
        """IsAdultProduct.

        :return:
            IsAdultProduct (string)
        """
        return self._safe_get_element_text(u'ItemAttributes.IsAdultProduct')

    @property
    def product_group(self):
        """ProductGroup.

        :return:
            ProductGroup (string)
        """
        return self._safe_get_element_text(u'ItemAttributes.ProductGroup')

    @property
    def product_type_name(self):
        """ProductTypeName.

        :return:
            ProductTypeName (string)
        """
        return self._safe_get_element_text(u'ItemAttributes.ProductTypeName')

    @property
    def formatted_price(self):
        """FormattedPrice.

        :return:
            FormattedPrice (string)
        """
        return self._safe_get_element_text(u'OfferSummary.LowestNewPrice.FormattedPrice')

    @property
    def running_time(self):
        """RunningTime.

        :return:
            RunningTime (string)
        """
        return self._safe_get_element_text(u'ItemAttributes.RunningTime')

    @property
    def studio(self):
        """Studio.

        :return:
            Studio (string)
        """
        return self._safe_get_element_text(u'ItemAttributes.Studio')

    @property
    def is_preorder(self):
        """IsPreorder (Is Preorder)

        :return:
            IsPreorder (string).
        """
        return self._safe_get_element_text(u'Offers.Offer.OfferListing.AvailabilityAttributes.IsPreorder')

    @property
    def availability(self):
        """Availability

        :return:
            Availability (string).
        """
        return self._safe_get_element_text(u'Offers.Offer.OfferListing.Availability')

    @property
    def availability_type(self):
        """AvailabilityAttributes.AvailabilityType

        :return:
            AvailabilityType (string).
        """
        return self._safe_get_element_text(u'Offers.Offer.OfferListing.AvailabilityAttributes.AvailabilityType')

    @property
    def availability_min_hours(self):
        """AvailabilityAttributes.MinimumHours

        :return:
            MinimumHours (string).
        """
        return self._safe_get_element_text(u'Offers.Offer.OfferListing.AvailabilityAttributes.MinimumHours')

    @property
    def availability_max_hours(self):
        """AvailabilityAttributes.MaximumHours

        :return:
            MaximumHours (string).
        """
        return self._safe_get_element_text(u'Offers.Offer.OfferListing.AvailabilityAttributes.MaximumHours')

    @property
    def detail_page_url(self):
        """DetailPageURL.

        :return:
            DetailPageURL (string)
        """
        return self._safe_get_element_text(u'DetailPageURL')

    @property
    def number_sellers(self):
        """Number of offers - New.

        :return:
            Number of offers - New (string)\
        """
        return self._safe_get_element_text(u'OfferSummary.TotalNew')

    @property
    def alternate_versions(self):
        """

        :return: List[Dict(title,asin,binding)]]
        """
        results = []
        alternate_versions = self._safe_get_element(u'AlternateVersions.AlternateVersion')
        if alternate_versions is not None:
            for alternate_version in alternate_versions:
                title = self._safe_get_element_text(u'Title', root=alternate_version)
                asin = self._safe_get_element_text(u'ASIN', root=alternate_version)
                binding = self._safe_get_element_text(u'Binding', root=alternate_version)
                av = {u'title': title, u'asin': asin, u'binding': binding}
                results.append(av)

        return results


class AmazonCart(_LXMLWrapper):
    """Wrapper around BottlenoseAmazon shopping cart.
       Allows iterating over Items in the cart.
    """

    @property
    def cart_id(self):
        return self._safe_get_element_text(u'Cart.CartId')

    @property
    def purchase_url(self):
        # type: () -> unicode
        return self._safe_get_element_text(u'Cart.PurchaseURL')

    @property
    def amount(self):
        return self._safe_get_element_text(u'Cart.SubTotal.Amount')

    @property
    def formatted_price(self):
        return self._safe_get_element_text(u'Cart.SubTotal.FormattedPrice')

    @property
    def currency_code(self):
        return self._safe_get_element_text(u'Cart.SubTotal.CurrencyCode')

    @property
    def hmac(self):
        return self._safe_get_element_text(u'Cart.HMAC')

    @property
    def url_encoded_hmac(self):
        return self._safe_get_element_text(u'Cart.URLEncodedHMAC')

    def __len__(self):
        return len(self._safe_get_element(u'Cart.CartItems.CartItem'))

    def __iter__(self):
        items = self._safe_get_element(u'Cart.CartItems.CartItem')
        if items is not None:
            for item in items:
                yield AmazonCartItem(item)

    def __getitem__(self, cart_item_id):
        """
        :param cart_item_id: access item by CartItemId
        :return: AmazonCartItem
        """
        for item in self:
            if item.cart_item_id == cart_item_id:
                return item
        raise KeyError(u'no item found with CartItemId: {0}'.format(cart_item_id, ))


class AmazonCartItem(_LXMLWrapper):
    @property
    def asin(self):
        return self._safe_get_element_text(u'ASIN')

    @property
    def quantity(self):
        """
        :return: int: quantity
        """
        return self._safe_get_element_text(u'Quantity')

    @property
    def cart_item_id(self):
        return self._safe_get_element_text(u'CartItemId')

    @property
    def title(self):
        return self._safe_get_element_text(u'Title')

    @property
    def product_group(self):
        return self._safe_get_element_text(u'ProductGroup')

    @property
    def formatted_price(self):
        return self._safe_get_element_text(u'Price.FormattedPrice')

    @property
    def amount(self):
        return self._safe_get_element_text(u'Price.Amount')

    @property
    def currency_code(self):
        return self._safe_get_element_text(u'Price.CurrencyCode')


class ItemNotAccessibleExeption(AmazonException):
    """This item is not accessible through the Product Advertising API.
    """
    pass
