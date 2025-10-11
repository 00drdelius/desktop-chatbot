-- dbname: chinamobile_internal_capabilities

-- 字段意思具体参考 ./model.py
create table wechat_reminder_source(
    index varchar(255) primary key not null,
    description varchar(255) not null,
    name varchar(255) not null,

    cycle varchar(10) not null,
    deadline TIMESTAMPTZ not null,
    repeat_count smallint not null,
    schedulers varchar(30)[] not null,
    executors varchar(30)[] not null
);

create table wechat_reminder_dynamic(
    index varchar(255) primary key not null,
    description varchar(255) not null,
    name varchar(255) not null,

    cycle varchar(10) not null,
    deadline TIMESTAMPTZ not null,
    repeat_count smallint not null,
    schedulers varchar(30)[] not null,
    executors_left varchar(30)[] not null,
    is_scheduled BOOLEAN DEFAULT FALSE
);

create table test(
    index varchar(255) primary key not null,
    description varchar(255) not null,
    name varchar(255) not null,

    cycle varchar(10) not null,
    deadline TIMESTAMPTZ not null,
    repeat_count smallint not null,
    schedulers varchar(30)[] not null,
    executors_left varchar(30)[] not null,
    is_scheduled BOOLEAN DEFAULT FALSE
);