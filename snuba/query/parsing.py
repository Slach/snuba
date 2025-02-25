from typing import List


class ParsingContext:
    """
    This class is passed around during the query parsing process
    to keep any state needed during the process itself (like the
    alias cache).
    """

    def __init__(self, sort_fields: bool = False) -> None:
        self.__alias_cache: List[str] = []
        self.sort_fields = sort_fields

    def add_alias(self, alias: str) -> None:
        self.__alias_cache.append(alias)

    def is_alias_present(self, alias: str) -> bool:
        return alias in self.__alias_cache
