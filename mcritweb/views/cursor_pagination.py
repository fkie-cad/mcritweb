from typing import Dict, Optional

from flask import Request, url_for


class CursorPagination:
    def __init__(self, request: Request, limit=10, query_param_prefix="", default_sort=None) -> None:
        self.default_limit = 10
        self.limit = limit
        self.query_param_prefix = query_param_prefix
        self.default_sort = default_sort

        self.cursor: Dict[str, Optional[str]] = {
            "first": None, # this will always stay None
            "forward": None,
            "backward": None,
            "current": None,
        }
        self.is_ascending = True
        self.sort_by = None

        # page is not really that important, it has no effect
        # we just count it so it looks like the normal pagination
        self.page = 1
        self.request_had_page = False

        self._readArgs(request.args)

        # used for link generation. 
        self.endpoint = request.endpoint
        self.original_args = dict(**request.view_args, **request.args)

    @property
    def cursor_param(self):
        prefix = self._get_args_prefix()
        return prefix+'cursor'

    @property
    def is_ascending_param(self):
        prefix = self._get_args_prefix()
        return prefix+'ascending'

    @property
    def sort_by_param(self):
        prefix = self._get_args_prefix()
        return prefix+'sort'

    @property
    def page_param(self):
        prefix = self._get_args_prefix()
        return prefix+'page'

    @property
    def limit_param(self):
        prefix = self._get_args_prefix()
        return prefix+'limit'

    @property
    def params_list(self):
        return [
            self.cursor_param,
            self.sort_by_param,
            self.is_ascending_param,
            self.page_param,
            self.limit_param,
        ]

    def _get_args_prefix(self):
        if self.query_param_prefix:
            return self.query_param_prefix + "_"
        else:
            return ""

    def _readArgs(self, args):
        self.cursor["current"] = args.get(self.cursor_param, None)
        self.is_ascending = args.get(self.is_ascending_param, "true").lower() != "false"
        self.sort_by = args.get(self.sort_by_param, self.default_sort)
        self.limit = self.default_limit if self.limit is None else self.limit
        self.page = 1
        try:
            self.page = int(args.get(self.page_param))
            self.request_had_page = True
            limit_value = int(args.get(self.limit_param))
            if limit_value in [10, 25, 50, 100, 250]:
                self.limit = limit_value
        except Exception:
            pass
    
    def _repairPage(self):
        # NOTE:
        # Here we could have some logic to detect if new insertions into DB
        # caused a "page 0" or even a "page -1" etc to exist.
        # Vice versa, deletions could make us loose page 1.
        # In those cases, we could shift the page numbers. 
        # But as this could be confusing as well... 
        # we will just ignore it for now.
        pass

    def _direction_to_page_num(self, direction):
        if direction == "forward":
            return self.page + 1
        elif direction == "backward":
            return self.page - 1
        elif direction == "current":
            return self.page
        elif direction == "first":
            return 1


    @property
    def hasForward(self):
        return self.cursor["forward"] is not None

    @property
    def hasBackward(self):
        return self.cursor["backward"] is not None

    @property
    def hasCurrent(self):
        return self.cursor["current"] is not None

    @property
    def is_first_page(self):
        """Whether this request is showing the first page of its result set.

        There are two ways to be on it and both have to count. A fresh URL carries
        no cursor at all. Paging *back* to it carries the backward cursor the second
        page handed out - `get_link("backward")`, which is what both the previous
        arrow and the "page 1" number link in table/pagination_widget.html emit - so
        "has no cursor" answers False for a page 1 the reader walked back to. A
        listing that drops the exact hit on the way back is issue #56 in mirror
        image: the record you searched for, gone from a page that showed it a moment
        earlier, under the same page number.

        The backend cannot answer this for us. `MinHashIndex._getSearchResultTemplate`
        sets a backward cursor for *any* request that carried one and returned rows,
        so `hasBackward` is true on a first page reached backwards; mcrit's cursor
        protocol has no "you are at the start" signal.

        `page` is this class's own bookkeeping, decremented by
        `_direction_to_page_num` on every backward link and carried in the query
        string, and it is the only thing that survives that round trip. It does not
        drive the query, and a hand-edited `?page=1&cursor=...` can lie about it -
        but the cost of that lie is one extra row for a record that does match the
        query, never a hidden one, and hiding is the failure this whole issue is
        about. `cursor["first"]` stays None so the "first" link is genuinely
        cursorless and lands here through the first clause.
        """
        return not self.cursor["current"] or self.page <= 1


    def _getArgs(self, direction="current"):
        result = {
            self.is_ascending_param: str(self.is_ascending).lower(),
        }
        if self.sort_by != self.default_sort:
            result[self.sort_by_param] = self.sort_by
        result[self.cursor_param] = self.cursor[direction]
        result[self.page_param] = self._direction_to_page_num(direction)
        return result
    
    #: The cursors that belong to the backend's answer. "current" comes from the
    #: request and "first" is always None, and `is_first_page` reads the former - so
    #: merge by name rather than blindly, or a new key in a future mcrit release
    #: would quietly change what that property means.
    RESULT_CURSOR_KEYS = ("forward", "backward")

    def read_cursor_from_result(self, result):
        if result is not None:
            for key in self.RESULT_CURSOR_KEYS:
                self.cursor[key] = result["cursor"].get(key)
            self._repairPage()

    def get_link(self, direction, **kwargs_overwrites):
        args = {}
        if self.original_args:
            args.update(self.original_args)
        args.update(kwargs_overwrites)
        args.update(self._getArgs(direction))
        url = url_for(self.endpoint, **args)
        return url
    
    def get_sort_link(self, sort_by, is_ascending, **kwargs_overwrites):
        args = {}
        if self.original_args:
            args.update(self.original_args)
        args.update(kwargs_overwrites)
        args.update({
            self.cursor_param: None, 
            self.page_param: 1, 
            self.sort_by_param: sort_by, 
            self.is_ascending_param: is_ascending, 
        })
        url = url_for(self.endpoint, **args)
        return url

    
    def getSearchParams(self):
        result = {
            "is_ascending": self.is_ascending,
            "cursor": self.cursor["current"],
        }
        if self.sort_by is not None:
            result["sort_by"] = self.sort_by
        return result

