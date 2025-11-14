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


    def _getArgs(self, direction="current"):
        result = {
            self.is_ascending_param: str(self.is_ascending).lower(),
        }
        if self.sort_by != self.default_sort:
            result[self.sort_by_param] = self.sort_by
        result[self.cursor_param] = self.cursor[direction]
        result[self.page_param] = self._direction_to_page_num(direction)
        return result
    
    def read_cursor_from_result(self, result):
        if result is not None:
            self.cursor.update(result["cursor"])
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

