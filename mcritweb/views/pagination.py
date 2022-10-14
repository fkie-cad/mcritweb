import math
from flask import Request, url_for


class Pagination(object):

    def __init__(self, request: Request, max_value: int, limit=50, query_param="p") -> None:
        self.page = self._getPageFromQueryParam(request, query_param)
        self.max_value = max_value
        self.limit = limit
        self._pagination_width = 2
        self.page = self.constrained_page

        # used for link generation. 
        self.endpoint = request.endpoint
        self.original_args = dict(**request.view_args, **request.args)
        self.query_param = query_param

    def _getPageFromQueryParam(self, request, query_param):
        page = 1
        try:
            page = int(request.args.get(query_param))
        except Exception:
            pass
        return max(1, page)

    @property
    def max_page(self):
        return max(1, math.ceil(self.max_value / self.limit))

    @property
    def constrained_page(self):
        return min(self.max_page, self.page)

    @property
    def pages(self):
        pages = []
        for index in [x for x in range(self.constrained_page - self._pagination_width, self.constrained_page + (self._pagination_width + 1))]:
            if index > 0 and index <= self.max_page:
                pages.append(index)
        if not pages:
            pages = [1]
        return pages

    @property
    def start_index(self):
        return (self.page - 1) * self.limit

    @property
    def end_index(self):
        return min((self.page - 1) * self.limit + self.limit, self.max_value)

    @property
    def page_index(self):
        pages = self.pages
        if self.constrained_page in pages:
            return pages.index(self.constrained_page)
        else:
            return pages.index(self.max_page)

    def get_link(self, page, **kwargs_overwrites):
        args = {}
        if self.original_args:
            args.update(self.original_args)
        args.update(kwargs_overwrites)
        args[self.query_param] = page
        url = url_for(self.endpoint, **args)
        return url


    def __repr__(self) -> str:
        return f"Pagination(p={self.page}, max_value={self.max_value}, limit={self.limit}) -> constrained_page={self.constrained_page}, start_index={self.start_index}, page_index={self.page_index}, max_page={self.max_page}, pages={self.pages}"
