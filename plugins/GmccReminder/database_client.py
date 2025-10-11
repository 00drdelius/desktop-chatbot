import os
from typing import *
from datetime import datetime
from contextlib import contextmanager

from psycopg_pool import ConnectionPool
import psycopg
from psycopg.rows import (
    tuple_row,dict_row, class_row,
    TupleRow, DictRow, T
)
from psycopg import Binary
from psycopg.adapt import PyFormat
import psycopg.sql as sql # always raise strange error, I rather use pure string

TYPE_CONVERTER={
    "timestamp without time zone":datetime,
    "character varying":str,
}

T = TypeVar("T")

@contextmanager
def get_database_client(tablename:str):
    database_client = DataBaseClient(
        host="localhost",
        dbname="chinamobile_internal_capabilities",
        user="postgres",
        password="postgres",
        tablename=tablename,
    )
    try:
        yield database_client
    finally:
        database_client.close()

class DataBaseClient:
    def __init__(
            self,
            host:str,
            dbname:str,
            user:str,
            password:str,
            tablename:str,
            row_factory: Literal["class_row", "dict_row", "tuple_row"],
            row_cls: type[T]=None
    ):
        self.db_pool = ConnectionPool(
            min_size=4, max_size=os.cpu_count(),
            open=True,
            kwargs=dict(
                host=host,
                dbname=dbname,
                user=user,
                password=password
            ),
        )
        match row_factory:
            case "class_row":
                assert row_cls!=None, "You need to pass a class if `class_row` is used"
                self.row_factory=class_row
            case "dict_row":
                self.row_factory=dict_row
            case "tuple_row":
                self.row_factory=tuple_row
            case _:
                raise TypeError(f"`DataBaseClient` got an unexpected row_factory: {row_factory}")
        
        self.tablename = tablename
        self.fields=[]
        self._init_fields()

    def execute(
        self,
        query:Union[sql.SQL, str],
        params: Union[Dict, Iterable]=None,
        fetch_type:Literal['one','many','all']='all',
        many_size:int=0,
        **kwargs
    ) -> Optional[Iterable]:
        result=None
        with self.db_pool.connection() as conn:
            try:
                with conn.cursor(row_factory=self.row_factory) as cur:
                    cur.execute(query, params, **kwargs)
                    if "SELECT" in query:
                        match fetch_type:
                            case "all":
                                result=cur.fetchall()
                            case "one":
                                result=cur.fetchone()
                            case "many":
                                result=cur.fetchmany(size=many_size)
                    else:
                        conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
        return result
    
    def stream(
        self,
        query:Union[sql.SQL, str],
        params: Union[Dict, Iterable]=None,
        size:int=1,
        **kwargs
    ) -> Iterator[Union[TupleRow, DictRow, type[T]]]:
        result=None
        with self.db_pool.connection() as conn:
            try:
                with conn.cursor(row_factory=self.row_factory) as cur:
                    for item in cur.stream(query, params, size=size, **kwargs):
                        yield item
            except Exception as e:
                conn.rollback()
                raise e
        return result

    def _init_fields(self):
        query = ("SELECT column_name, data_type, is_nullable "
                 "FROM information_schema.columns "
                f"WHERE table_name='{self.tablename}'")

        for field_item in self.stream(query,):
            if field_item.get("is_nullable",'YES')=='NO':
                self.fields.append(field_item['column_name'])

    def insert_item(self,items:dict):
        """
        insert into table with fields and values set.
        Args:
            items(dict): dict contains keys matched fields of table.
        """
        self._check_fields(items.keys())

        params=[]
        placeholders=[]
        field_identifiers=[]
        for k,v in items.items():
            field_identifiers.append(k)

            if isinstance(v,bytes):
                params.append(Binary(v))
                placeholders.append("%b")
            else:
                params.append(v)
                placeholders.append("%s")

        str_query ="INSERT INTO {table} ({fields}) VALUES ({values})".format(
                table=self.tablename,
                fields=", ".join(field_identifiers),
                values=", ".join(placeholders)
            )
        self.execute(str_query, params, )


    def update_item_by_conditions(
            self,
            items:dict,
            condition_items:Dict[str, Any],
    ):
        """
        update fields by conditions
        Args:
            items(dict): dict contains keys matched fields of table.
            condition_items(Dict[str, Any]): {cond-field1: cond-value1, cond-field2: cond-value2, ...}
        """
        self._check_fields(items.keys())
        self._check_fields(condition_items.keys())

        update_str_list = []
        update_params=[]
        for k,v in items.items():
            single_str=f"{k}="
            if isinstance(v, bytes):
                single_str+="%b"
                update_params.append(Binary(v))
            else:
                single_str+="%s"
                update_params.append(v)
            update_str_list.append(single_str)

        conditional_str_list=[]
        cond_params=[]
        for k, v in condition_items.items():
            single_str=f"{k}=%s"
            conditional_str_list.append(single_str)
            cond_params.append(v)

        str_query=(
            "UPDATE {}\n".format(self.tablename)
            +"SET {}\n".format(", ".join(update_str_list))
            +"WHERE {}".format(" AND ".join(conditional_str_list))
        )
        self.execute(str_query, params=update_params+cond_params)

    def query_fields(
            self,
            expected_fields:Iterable,
            condition_items:Dict[str, Any]={},
            limit:int=None
    ):
        """
        query fields by conditions, conditions combined with `AND`.
        Args:
            expected_fields(Iterable): [expected field1, expected field2, ...], or ['*'] to search all
            condition_items(Dict[str, Any]): {cond-field1: cond-value1, cond-field2: cond-value2, ...}, could be `None`
        """
        self._check_fields(expected_fields)
        self._check_fields(condition_items.keys())

        conditional_str_list=[]
        params=[]
        for k, v in condition_items.items():
            single_str=f"{k}=%s"
            conditional_str_list.append(single_str)
            params.append(v)

        str_query="SELECT {fields} from {tablename}".format(
            fields=", ".join(expected_fields),
            tablename=self.tablename,
        )
        if any(conditional_str_list):
            str_query="{str_query} WHERE {cond_str}".format(
                str_query=str_query,
                cond_str=" AND ".join(conditional_str_list)
            )

        if limit: str_query+=f" LIMIT {limit}"

        for row in self.stream(str_query,params=params):
            yield row

    def _check_fields(self, unchecked_fields:Iterable):
        "TODO: null fields check; type check"
        # if "*" in unchecked_fields:
            # return
        # diff = (set(unchecked_fields)).difference(set(self.fields))
        # assert not any(diff), f"not-null fields not satisfied. Still left: {str(diff)}"
        ...

    def close(self):
        self.db_pool.close()
