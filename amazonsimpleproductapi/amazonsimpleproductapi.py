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

from decimal import Decimal
from lxml import etree, objectify
from lxml.etree import Element

try:
    # noinspection PyUnresolvedReferences
   from typing import Any, Iterable, Optional, Dict, List, Tuple, AnyStr, Set
except ImportError:
    pass

from calibre_plugins.AmazonProductAdvertisingAPI.bottlenose.bottlenose import BottlenoseAmazon, BottlenoseAmazonCall


class AmazonException(Exception):
    """Base Class for BottlenoseAmazon Api Exceptions.
    """
    pass


class CartException(AmazonException):
    """Cart related Exception
    """
    pass


class CartInfoMismatchException(CartException):
    """HMAC, CartId and AssociateTag did not match
    """
    pass


class AsinNotFoundException(AmazonException):
    """ASIN Not Found Exception.
    """
    pass


class LookupException(AmazonException):
    """Lookup Exception.
    """
    pass


class SearchException(AmazonException):
    """Search Exception.
    """
    pass


class NoMorePagesException(SearchException):
    """No More Pages Exception.
    """
    pass


class RequestThrottledException(AmazonException):
    """Exception for when BottlenoseAmazon has throttled a request, per:
    http://docs.aws.amazon.com/AWSECommerceService/latest/DG/ErrorNumbers.html
    """
    pass


class SimilartyLookupException(AmazonException):
    """Similarty Lookup Exception.
    """
    pass


class BrowseNodeLookupException(AmazonException):
    """Browse Node Lookup Exception.
    """
    pass


class AmazonAPI(object):
    # https://kdp.amazon.com/help?topicId=A1CT8LK6UW2FXJ
    AMAZON_DOMAINS = {
        'CA': 'ca',
        'DE': 'de',
        'ES': 'es',
        'FR': 'fr',
        'IN': 'in',
        'IT': 'it',
        'JP': 'co.jp',
        'UK': 'co.uk',
        'US': 'com',
        'CN': 'cn'
    }

    AMAZON_ASSOCIATES_BASE_URL = 'http://www.amazon.{domain}/dp/'

    # noinspection PyTypeChecker
    def __init__(self, aws_key, aws_secret, aws_associate_tag, **kwargs):
        # type: (AnyStr, AnyStr, AnyStr, Dict[Any]) -> AmazonAPI
        """Initialize an BottlenoseAmazon API Proxy.

        kwargs values are passed directly to Bottlenose. Check the Bottlenose
        API for valid values (some are provided below).
        For legacy support, the older 'region' value is still supported.
        Code should be updated to use the Bottlenose 'Region' value
        instead.

        :type kwargs: Dict[Any]
        :param aws_key:
            A string representing an AWS authentication key.
        :param aws_secret:
            A string representing an AWS authentication secret.
        :param aws_associate_tag:
            A string representing an AWS associate tag.

        Important Bottlenose arguments:
        :param Region:
            ccTLD you want to search for products on (e.g. 'UK'
            for amazon.co.uk).
            See keys of bottlenose.api.AMAZON_SERVICE_DOMAINS for options, which were
            CA, CN, DE, ES, FR, IT, JP, UK, US at the time of writing.
            Must be uppercase. Default is 'US' (amazon.com).
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
        # support older style calls
        if 'region' in kwargs:
            kwargs['Region'] = kwargs['region']
            del kwargs['region']

        if 'Version' not in kwargs:
            kwargs['Version'] = '2013-08-01'

        self.api = BottlenoseAmazon(AWSAccessKeyId=aws_key, AWSSecretAccessKey=aws_secret,
                 AssociateTag=aws_associate_tag, **kwargs)
        self.aws_associate_tag = aws_associate_tag
        self.region = kwargs.get('region', 'US')

    def lookup(self, ResponseGroup="Large", **kwargs):
        # type: (AnyStr, Optional[Any]) -> Iterable[AmazonProduct]
        """Lookup an BottlenoseAmazon Product.
        :param ResponseGroup:API response group
        :param kwargs:
        :return: a list of  :class:`~.AmazonProduct` instances if multiple
            items where returned.
        """
        response = self.api.ItemLookup(ResponseGroup=ResponseGroup, **kwargs)
        root = objectify.fromstring(response)
        if root.Items.Request.IsValid == 'False':
            code = root.Items.Request.Errors.Error.Code
            msg = root.Items.Request.Errors.Error.Message
            raise LookupException("BottlenoseAmazon Product Lookup Error: '{0}', '{1}'".format(code, msg))
        if not hasattr(root.Items, 'Item'):
            raise AsinNotFoundException("ASIN(s) not found: '{0}'".format(etree.tostring(root, pretty_print=True)))
        return [AmazonProduct(item=item, aws_associate_tag=self.aws_associate_tag, api=self.api,
                              region=self.region) for item in getattr(root.Items, 'Item', [])]

    def lookup_bulk(self, ResponseGroup="Large", **kwargs):
        # type: (AnyStr, Optional[Any]) -> List[AmazonProduct]
        """Lookup BottlenoseAmazon Products in bulk.

        Returns all products matching requested ASINs, ignoring invalid
        entries.

        :return: Iterable[AmazonProduct]: A list of  :class:`~.AmazonProduct`instances.
        """
        response = self.api.ItemLookup(ResponseGroup=ResponseGroup, **kwargs)
        root = objectify.fromstring(response)
        if not hasattr(root.Items, 'Item'):
            return []
        return list(
            AmazonProduct(item=item, aws_associate_tag=self.aws_associate_tag, api=self.api, region=self.region)
            for item in root.Items.Item
        )

    def similarity_lookup(self, ResponseGroup="Large", **kwargs):
        # type: (AnyStr, Dict[Any]) -> List[AmazonProduct]
        """Similarty Lookup.

        Returns up to ten products that are similar to all items
        specified in the request.

        Example:
            api.similarity_lookup(ItemId='B002L3XLBO,B000LQTBKI')
        """
        response = self.api.SimilarityLookup(
            ResponseGroup=ResponseGroup, **kwargs)
        root = objectify.fromstring(response)
        if root.Items.Request.IsValid == 'False':
            code = root.Items.Request.Errors.Error.Code
            msg = root.Items.Request.Errors.Error.Message
            raise SimilartyLookupException(
                "BottlenoseAmazon Similarty Lookup Error: '{0}', '{1}'".format(
                    code, msg))
        return [
            AmazonProduct(item=item, aws_associate_tag=self.aws_associate_tag,
                api=self.api, region=self.region)
            for item in getattr(root.Items, 'Item', [])
        ]

    def browse_node_lookup(self, ResponseGroup="BrowseNodeInfo", **kwargs):
        # type: (AnyStr, Optional[Any]) -> List[AmazonBrowseNode]
        """Browse Node Lookup.

        Returns the specified browse node's name, children, and ancestors.
        Example:
            api.browse_node_lookup(BrowseNodeId='163357')
        """
        response = self.api.BrowseNodeLookup(
            ResponseGroup=ResponseGroup, **kwargs)
        root = objectify.fromstring(response)
        if root.BrowseNodes.Request.IsValid == 'False':
            code = root.BrowseNodes.Request.Errors.Error.Code
            msg = root.BrowseNodes.Request.Errors.Error.Message
            raise BrowseNodeLookupException(
                "BottlenoseAmazon BrowseNode Lookup Error: '{0}', '{1}'".format(
                    code, msg))
        return [AmazonBrowseNode(node.BrowseNode) for node in root.BrowseNodes]

    def search(self, timeout=30, **kwargs):
        # type: (int, Optional[Any]) -> AmazonSearch
        """Search.

        :param timeout:int:timeout
        :return: AmazonSearch
        :param kwargs:
        :type kwargs: Text
        :rtype: AmazonSearch
        """
        region = kwargs.get('region', self.region)
        kwargs.update({'region': region})
        return AmazonSearch(api=self.api,aws_associate_tag=self.aws_associate_tag,timeout=timeout**kwargs)

    def search_n(self, n, **kwargs):
        # type: (int, Optional[Any]) -> List[AmazonProduct]
        """Search and return first N results..

        :param kwargs: AnyStr: parameters
        :param n: Integer: An integer specifying the number of results to return.
        :return: List[AmazonProduct]: A list of :class:`~.AmazonProduct`.
        """
        region = kwargs.get('region', self.region)
        kwargs.update({'region': region})


        items = AmazonSearch(api=self.api, aws_associate_tag=self.aws_associate_tag, **kwargs)
        products=[]
        for i in items:
            products.append(i)
            if len(products) >= n:
                break
        
        return products

class LXMLWrapper(object):
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
            String path (i.e. 'Items.Item.Offers.Offer').
        :return:
            Element or None.
        """
        elements = path.split('.')
        parent = root if root is not None else self.parsed_response
        for element in elements[:-1]:
            parent = getattr(parent, element, None)
            if parent is None:
                return None
        return getattr(parent, elements[-1], None)

    def _safe_get_element_text(self, path, root=None):
        # type: (Element, [AnyStr or None]) -> AnyStr or None
        """Safe get element text.

        Get element as string or None,
        :rtype: Text or None
        :param root: Lxml element.
        :param path: String path (i.e. 'Items.Item.Offers.Offer').
        :return: AnyStr or None
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
            String path (i.e. 'Items.Item.Offers.Offer').
        :return:
            datetime.date or None.
        """
        value = self._safe_get_element_text(path=path, root=root)
        if value is not None:
            try:
                from datetime import datetime
                value = datetime.strptime(value, '%Y-%m-%d')
                if value:
                    value = value.date()
            except ValueError:
                value = None

        return value


class AmazonSearch(object):
    """ BottlenoseAmazon Search.

    A class providing an iterable over amazon search results.
    """

    def __init__(self, api, aws_associate_tag, **kwargs):
        # type: (BottlenoseAmazonCall, Optional[Any]) -> AmazonSearch
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
        self.aws_associate_tag = aws_associate_tag

    def __iter__(self):
        # type: () -> AmazonProduct
        """Iterate.

        A generator which iterate over all paginated results
        returning :class:`~.AmazonProduct` for each item.

        :return:
            Yields a :class:`~.AmazonProduct` for each result item.
        """
        for page in self.iterate_pages():
            for item in getattr(page.Items, 'Item', []):
                yield AmazonProduct(item=item,aws_associate_tag=self.aws_associate_tag, api=self.api, **self.kwargs)

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

    def _query(self, ResponseGroup="Large", **kwargs):
        """Query.

        Query BottlenoseAmazon search and check for errors.

        :return:
            An lxml root element.
        """
        response = self.api.ItemSearch(ResponseGroup=ResponseGroup, **kwargs)
        root = objectify.fromstring(response)
        if (hasattr(root.Items.Request, 'Errors') and
                not hasattr(root.Items, 'Item')):
            code = root.Items.Request.Errors.Error.Code
            msg = root.Items.Request.Errors.Error.Message
            if code == 'AWS.ParameterOutOfRange':
                raise NoMorePagesException(msg)
            elif code == 'HTTP Error 503':
                raise RequestThrottledException(
                    "Request Throttled Error: '{0}', '{1}'".format(code, msg))
            else:
                raise SearchException(
                    "BottlenoseAmazon Search Error: '{0}', '{1}'".format(code, msg))
        if hasattr(root.Items, 'TotalPages'):
            if root.Items.TotalPages == self.current_page:
                self.is_last_page = True
        return root


class AmazonBrowseNode(LXMLWrapper):
    @property
    def id(self):
        """Browse Node ID.

        A positive integer that uniquely identifies a parent product category.

        :return:
            ID (integer)
        """
        if hasattr(self.parsed_response, 'BrowseNodeId'):
            return int(self.parsed_response['BrowseNodeId'])
        return None

    @property
    def name(self):
        """Browse Node Name.

        :return:
            Name (string)
        """
        return getattr(self.parsed_response, 'Name', None)

    @property
    def is_category_root(self):
        """Boolean value that specifies if the browse node is at the top of
        the browse node tree.
        """
        return getattr(self.parsed_response, 'IsCategoryRoot', False)

    @property
    def ancestor(self):
        """This browse node's immediate ancestor in the browse node tree.

        :return:
            The ancestor as an :class:`~.AmazonBrowseNode`, or None.
        """
        ancestors = getattr(self.parsed_response, 'Ancestors', None)
        if hasattr(ancestors, 'BrowseNode'):
            return AmazonBrowseNode(ancestors['BrowseNode'])
        return None

    @property
    def ancestors(self):
        """A list of this browse node's ancestors in the browse node tree.

        :return:
            List of :class:`~.AmazonBrowseNode` objects.
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
        child_nodes = getattr(self.parsed_response, 'Children')
        for child in getattr(child_nodes, 'BrowseNode', []):
            children.append(AmazonBrowseNode(child))
        return children


class AmazonProduct(LXMLWrapper):
    """A wrapper class for an BottlenoseAmazon product.
    """

    # noinspection PyUnusedLocal
    def __init__(self, item, aws_associate_tag, api, region='US', MaxQPS=0.9, **kwargs):
        # type: (Element, AnyStr, BottlenoseAmazonCall, Optional[AnyStr], Optional[Any]) -> ([AmazonProduct])
        """Initialize an BottlenoseAmazon Product Proxy.

        :type kwargs: object
        :param aws_associate_tag: AnyStr: Your associate tag
        :param api: BottlenoseAmazon: BottlenoseAmazon api
        :param item: Element: Lxml Item element.
        """
        super(AmazonProduct, self).__init__(item)
        self.aws_associate_tag = aws_associate_tag
        self.api = api
        self.parent = None
        self.MaxQPS = MaxQPS
        self.region = region

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

    @property
    def price_and_currency(self):
        # type: () -> Tuple[Optional[float],Optional[AnyStr]]
        """Get Offer Price and Currency.

        Return price according to the following process:

        * If product has a sale return Sales Price, otherwise,
        * Return Price, otherwise,
        * Return lowest offer price, otherwise,
        * Return None.

        :return:
            A tuple containing:

                1. Decimal representation of price.
                2. ISO Currency code (string).
        """
        price = self._safe_get_element_text(
            'Offers.Offer.OfferListing.SalePrice.Amount')
        if price:
            currency = self._safe_get_element_text(
                'Offers.Offer.OfferListing.SalePrice.CurrencyCode')
        else:
            price = self._safe_get_element_text(
                'Offers.Offer.OfferListing.Price.Amount')
            if price:
                currency = self._safe_get_element_text(
                    'Offers.Offer.OfferListing.Price.CurrencyCode')
            else:
                price = self._safe_get_element_text(
                    'OfferSummary.LowestNewPrice.Amount')
                currency = self._safe_get_element_text(
                    'OfferSummary.LowestNewPrice.CurrencyCode')
        if price:
            dprice = Decimal(
                price) / 100 if 'JP' not in self.region else Decimal(price)
            return dprice, currency
        else:
            return None, None

    @property
    def offer_id(self):
        """Offer ID

        :return:
            Offer ID (string).
        """
        return self._safe_get_element(
            'Offers.Offer.OfferListing.OfferListingId')

    @property
    def asin(self):
        """ASIN (BottlenoseAmazon ID)

        :return:
            ASIN (string).
        """
        return self._safe_get_element_text('ASIN')

    @property
    def sales_rank(self):
        """Sales Rank

        :return:
            Sales Rank (integer).
        """
        return self._safe_get_element_text('SalesRank')

    @property
    def offer_url(self):
        """Offer URL

        :return:
            Offer URL (string).
        """
        return "{0}{1}/?tag={2}".format(
            AmazonAPI.AMAZON_ASSOCIATES_BASE_URL.format(domain=AmazonAPI.AMAZON_DOMAINS[self.region]),
            self.asin,
            self.aws_associate_tag)

    @property
    def author(self):
        """Author.
        Depricated, please use `authors`.

        :return:
            Author (string).
        """
        import warnings
        warnings.warn("deprecated", DeprecationWarning)
        authors = self.authors
        if len(authors):
            return authors[0]
        else:
            return None

    @property
    def authors(self):
        """Authors.

        :return:List[AnyStr]:Returns of list of authors
        """
        result = []
        authors = self._safe_get_element('ItemAttributes.Author')
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
        creators = self._safe_get_element('ItemAttributes.Creator')
        if creators is not None:
            for creator in creators:
                role = creator.attrib['Role'] if \
                    'Role' in creator.attrib else None
                result.append((creator.text, role))
        return result

    @property
    def publisher(self):
        """Publisher.

        :return:
            Publisher (string)
        """
        return self._safe_get_element_text('ItemAttributes.Publisher')

    @property
    def label(self):
        """Label.

        :return:
            Label (string)
        """
        return self._safe_get_element_text('ItemAttributes.Label')

    @property
    def manufacturer(self):
        """Manufacturer.

        :return:
            Manufacturer (string)
        """
        return self._safe_get_element_text('ItemAttributes.Manufacturer')

    @property
    def brand(self):
        """Brand.

        :return:
            Brand (string)
        """
        return self._safe_get_element_text('ItemAttributes.Brand')

    @property
    def isbn(self):
        """ISBN.

        :return:
            ISBN (string)
        """
        return self._safe_get_element_text('ItemAttributes.ISBN')

    @property
    def eisbn(self):
        """EISBN (The ISBN of eBooks).

        :return:
            EISBN (string)
        """
        return self._safe_get_element_text('ItemAttributes.EISBN')

    @property
    def binding(self):
        """Binding.

        :return:
            Binding (string)
        """
        return self._safe_get_element_text('ItemAttributes.Binding')

    @property
    def pages(self):
        """Pages.

        :return:
            Pages (string)
        """
        return self._safe_get_element_text('ItemAttributes.NumberOfPages')

    @property
    def publication_date(self):
        """Pubdate.

        :return:
            Pubdate (datetime.date)
        """
        return self._safe_get_element_date('ItemAttributes.PublicationDate')

    @property
    def release_date(self):
        """Release date .

        :return:
            Release date (datetime.date)
        """
        return self._safe_get_element_date('ItemAttributes.ReleaseDate')

    @property
    def edition(self):
        """Edition.

        :return:
            Edition (string)
        """
        return self._safe_get_element_text('ItemAttributes.Edition')

    @property
    def large_image_url(self):
        """Large Image URL.

        :return:
            Large image url (string)
        """
        return self._safe_get_element_text('LargeImage.URL')

    @property
    def medium_image_url(self):
        """Medium Image URL.

        :return:
            Medium image url (string)
        """
        return self._safe_get_element_text('MediumImage.URL')

    @property
    def small_image_url(self):
        """Small Image URL.

        :return:
            Small image url (string)
        """
        return self._safe_get_element_text('SmallImage.URL')

    @property
    def tiny_image_url(self):
        """Tiny Image URL.

        :return:
            Tiny image url (string)
        """
        return self._safe_get_element_text('TinyImage.URL')

    @property
    def reviews(self):
        """Customer Reviews.

        Get a iframe URL for customer reviews.

        :return:
            A tuple of: has_reviews (bool), reviews url (string)
        """
        iframe = self._safe_get_element_text('CustomerReviews.IFrameURL')
        has_reviews = self._safe_get_element_text('CustomerReviews.HasReviews')
        if has_reviews is not None and has_reviews == 'true':
            has_reviews = True
        else:
            has_reviews = False
        return has_reviews, iframe

    @property
    def ean(self):
        # type: () -> AnyStr
        """EAN.

        :return:
            EAN (string)
        """
        ean = self._safe_get_element_text('ItemAttributes.EAN')
        if ean is None:
            ean_list = self._safe_get_element_text('ItemAttributes.EANList')
            if ean_list:
                ean = self._safe_get_element_text(
                    'EANListElement', root=ean_list[0])
        return ean

    @property
    def upc(self):
        """UPC.

        :return:
            UPC (string)
        """
        upc = self._safe_get_element_text('ItemAttributes.UPC')
        if upc is None:
            upc_list = self._safe_get_element_text('ItemAttributes.UPCList')
            if upc_list:
                upc = self._safe_get_element_text(
                    'UPCListElement', root=upc_list[0])
        return upc

    @property
    def color(self):
        """Color.

        :return:
            Color (string)
        """
        return self._safe_get_element_text('ItemAttributes.Color')

    @property
    def sku(self):
        """SKU.

        :return:
            SKU (string)
        """
        return self._safe_get_element_text('ItemAttributes.SKU')

    @property
    def mpn(self):
        """MPN.

        :return:
            MPN (string)
        """
        return self._safe_get_element_text('ItemAttributes.MPN')

    @property
    def model(self):
        """Model Name.

        :return:
            Model (string)
        """
        return self._safe_get_element_text('ItemAttributes.Model')

    @property
    def part_number(self):
        """Part Number.

        :return:
            Part Number (string)
        """
        return self._safe_get_element_text('ItemAttributes.PartNumber')

    @property
    def title(self):
        """Title.

        :return:
            Title (string)
        """
        return self._safe_get_element_text('ItemAttributes.Title')

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
        return ''

    @property
    def editorial_reviews(self):
        """Editorial Review.

        Returns a list of all editorial reviews.

        :return:
            A list containing:

                Editorial Review (string)
        """
        result = []
        reviews_node = self._safe_get_element('EditorialReviews')

        if reviews_node is not None:
            for review_node in reviews_node.iterchildren():
                content_node = getattr(review_node, 'Content')
                if content_node is not None:
                    result.append(content_node.text)
        return result

    @property
    def languages(self):
        # type: () -> Set[AnyStr]
        """Languages.

        Returns a set of languages in lower-case.

        :return:
            Returns a set of languages in lower-case (strings).
        """
        result = set()
        languages = self._safe_get_element('ItemAttributes.Languages')
        if languages is not None:
            for language in languages.iterchildren():
                text = self._safe_get_element_text('Name', language)
                if text:
                    result.add(text.lower())
        return result

    @property
    def features(self):
        """Features.

        Returns a list of feature descriptions.

        :return:
            Returns a list of 'ItemAttributes.Feature' elements (strings).
        """
        result = []
        features = self._safe_get_element('ItemAttributes.Feature')
        if features is not None:
            for feature in features:
                result.append(feature.text)
        return result

    @property
    def list_price(self):
        """List Price.

        :return:
            A tuple containing:

                1. Decimal representation of price.
                2. ISO Currency code (string).
        """
        price = self._safe_get_element_text('ItemAttributes.ListPrice.Amount')
        currency = self._safe_get_element_text(
            'ItemAttributes.ListPrice.CurrencyCode')
        if price:
            dprice = Decimal(
                price) / 100 if 'JP' not in self.region else Decimal(price)
            return dprice, currency
        else:
            return None, None

    def get_attribute(self, name):
        """Get Attribute

        Get an attribute (child elements of 'ItemAttributes') value.

        :param name:
            Attribute name (string)
        :return:
            Attribute value (string) or None if not found.
        """
        return self._safe_get_element_text("ItemAttributes.{0}".format(name))

    def get_attribute_details(self, name):
        """Get Attribute Details

        Gets XML attributes of the product attribute. These usually contain
        details about the product attributes such as units.

        :param name:
            Attribute name (string)
        :return:
            A name/value dictionary.
        """
        return self._safe_get_element("ItemAttributes.{0}".format(name)).attrib

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
        return self._safe_get_element('ParentASIN')

    def get_parent(self):
        # type: () -> AmazonProduct
        """Get Parent.

        Fetch parent product if it exists.
        Use `parent_asin` to check if a parent exist before fetching.

        :return:
            An instance of :class:`~.AmazonProduct` representing the
            parent product.
        """
        if not self.parent:
            parent = self._safe_get_element('ParentASIN')
            if parent:
                self.parent = self.api.lookup(ItemId=parent)
        return self.parent

    @property
    def browse_nodes(self):
        """Browse Nodes.

        :return:
            A list of :class:`~.AmazonBrowseNode` objects.
        """
        root = self._safe_get_element('BrowseNodes')
        if root is None:
            return []

        return [AmazonBrowseNode(child) for child in root.iterchildren()]

    @property
    def images(self):
        """List of images for a response.
        When using lookup with RespnoseGroup 'Images', you'll get a
        list of images. Parse them so they are returned in an easily
        used list format.

        :return:
            A list of `ObjectifiedElement` images
        """
        try:
            images = [image for image in self._safe_get_element(
                'ImageSets.ImageSet')]
        except TypeError:  # No images in this ResponseGroup
            images = []
        return images

    @property
    def genre(self):
        """Movie Genre.

        :return:
            The genre of a movie.
        """
        return self._safe_get_element_text('ItemAttributes.Genre')

    @property
    def actors(self):
        """
        :return:List(AnyStr):A list of actors names.
        """
        result = []
        actors = self._safe_get_element('ItemAttributes.Actor') or []
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
        directors = self._safe_get_element('ItemAttributes.Director') or []
        for director in directors:
            result.append(director.text)
        return result

    @property
    def is_adult(self):
        """IsAdultProduct.

        :return:
            IsAdultProduct (string)
        """
        return self._safe_get_element_text('ItemAttributes.IsAdultProduct')

    @property
    def product_group(self):
        """ProductGroup.

        :return:
            ProductGroup (string)
        """
        return self._safe_get_element_text('ItemAttributes.ProductGroup')

    @property
    def product_type_name(self):
        """ProductTypeName.

        :return:
            ProductTypeName (string)
        """
        return self._safe_get_element_text('ItemAttributes.ProductTypeName')

    @property
    def formatted_price(self):
        """FormattedPrice.

        :return:
            FormattedPrice (string)
        """
        return self._safe_get_element_text(
            'OfferSummary.LowestNewPrice.FormattedPrice')

    @property
    def running_time(self):
        """RunningTime.

        :return:
            RunningTime (string)
        """
        return self._safe_get_element_text('ItemAttributes.RunningTime')

    @property
    def studio(self):
        """Studio.

        :return:
            Studio (string)
        """
        return self._safe_get_element_text('ItemAttributes.Studio')

    @property
    def is_preorder(self):
        """IsPreorder (Is Preorder)

        :return:
            IsPreorder (string).
        """
        return self._safe_get_element_text(
            'Offers.Offer.OfferListing.AvailabilityAttributes.IsPreorder')

    @property
    def availability(self):
        """Availability

        :return:
            Availability (string).
        """
        return self._safe_get_element_text(
            'Offers.Offer.OfferListing.Availability')

    @property
    def availability_type(self):
        """AvailabilityAttributes.AvailabilityType

        :return:
            AvailabilityType (string).
        """
        return self._safe_get_element_text(
            'Offers.Offer.OfferListing.AvailabilityAttributes.AvailabilityType'
        )

    @property
    def availability_min_hours(self):
        """AvailabilityAttributes.MinimumHours

        :return:
            MinimumHours (string).
        """
        return self._safe_get_element_text(
            'Offers.Offer.OfferListing.AvailabilityAttributes.MinimumHours')

    @property
    def availability_max_hours(self):
        """AvailabilityAttributes.MaximumHours

        :return:
            MaximumHours (string).
        """
        return self._safe_get_element_text(
            'Offers.Offer.OfferListing.AvailabilityAttributes.MaximumHours')

    @property
    def detail_page_url(self):
        """DetailPageURL.

        :return:
            DetailPageURL (string)
        """
        return self._safe_get_element_text('DetailPageURL')

    @property
    def number_sellers(self):
        """Number of offers - New.

        :return:
            Number of offers - New (string)\
        """
        return self._safe_get_element_text('OfferSummary.TotalNew')

    @property
    def alternate_versions(self):
        """

        :return: List[Dict(title,asin,binding)]]
        """
        results = []
        alternate_versions = self._safe_get_element('AlternateVersions.AlternateVersion')
        if alternate_versions is not None:
            for alternate_version in alternate_versions:
                title = self._safe_get_element_text('Title', root=alternate_version)
                asin = self._safe_get_element_text('ASIN', root=alternate_version)
                binding = self._safe_get_element_text('Binding', root=alternate_version)
                av = dict(title=title, asin=asin, binding=binding)
                results.append(av)

        return results


class AmazonCart(LXMLWrapper):
    """Wrapper around BottlenoseAmazon shopping cart.
       Allows iterating over Items in the cart.
    """

    @property
    def cart_id(self):
        return self._safe_get_element_text('Cart.CartId')

    @property
    def purchase_url(self):
        return self._safe_get_element_text('Cart.PurchaseURL')

    @property
    def amount(self):
        return self._safe_get_element_text('Cart.SubTotal.Amount')

    @property
    def formatted_price(self):
        return self._safe_get_element_text('Cart.SubTotal.FormattedPrice')

    @property
    def currency_code(self):
        return self._safe_get_element_text('Cart.SubTotal.CurrencyCode')

    @property
    def hmac(self):
        return self._safe_get_element_text('Cart.HMAC')

    @property
    def url_encoded_hmac(self):
        return self._safe_get_element_text('Cart.URLEncodedHMAC')

    def __len__(self):
        return len(self._safe_get_element('Cart.CartItems.CartItem'))

    def __iter__(self):
        items = self._safe_get_element('Cart.CartItems.CartItem')
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
        raise KeyError(
            'no item found with CartItemId: {0}'.format(cart_item_id, ))


class AmazonCartItem(LXMLWrapper):
    @property
    def asin(self):
        return self._safe_get_element_text('ASIN')

    @property
    def quantity(self):
        return self._safe_get_element_text('Quantity')

    @property
    def cart_item_id(self):
        return self._safe_get_element_text('CartItemId')

    @property
    def title(self):
        return self._safe_get_element_text('Title')

    @property
    def product_group(self):
        return self._safe_get_element_text('ProductGroup')

    @property
    def formatted_price(self):
        return self._safe_get_element_text('Price.FormattedPrice')

    @property
    def amount(self):
        return self._safe_get_element_text('Price.Amount')

    @property
    def currency_code(self):
        return self._safe_get_element_text('Price.CurrencyCode')
