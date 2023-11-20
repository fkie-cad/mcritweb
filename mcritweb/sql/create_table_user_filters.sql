DROP TABLE IF EXISTS user_filters;

CREATE TABLE user_filters (
  user_id INTEGER PRIMARY KEY,
  filter_direct_min_score INTEGER,
  filter_direct_nonlib_min_score INTEGER,
  filter_frequency_min_score INTEGER,
  filter_frequency_nonlib_min_score INTEGER,
  filter_unique_only INTEGER,
  filter_exclude_own_family INTEGER,
  filter_function_min_score INTEGER,
  filter_function_max_score INTEGER,
  filter_max_num_families INTEGER,
  filter_exclude_library INTEGER,
  filter_exclude_pic INTEGER
);
