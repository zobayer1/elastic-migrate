#!/bin/bash
# This script creates a test directory for holding schema files used to run test
# configure target directory name to hold test schema files
dirname='tests/resources/schema_dir'

# create directory silently or exit on fail
rm -rf $dirname || exit $?
mkdir -p $dirname || exit $?

# create file V1_1__create_index_mapping_for_twitter.exm
cat << EOF > "$dirname/V1_1__create_index_mapping_for_twitter.exm"
PUT twitter
PUT twitter/_mapping/doc
{
  "dynamic": "strict",
  "properties": {
    "username": {
      "type": "text"
    }
  }
}
EOF

# create file V1_2__create_new_doc_in_twitter.exm
cat << EOF > "$dirname/V1_2__create_new_doc_in_twitter.exm"
POST twitter/doc
{
  "username": "Zobayer"
}
POST twitter/doc
{
  "username": "Saki"
}
POST twitter/doc/1
{
  "username": "Zobayer1"
}
POST twitter/doc/2
{
  "username": "Zobayer2"
}
EOF

# create file V1_3__update_existing_doc_in_twitter.exm
cat << EOF > "$dirname/V1_3__update_existing_doc_in_twitter.exm"
PUT twitter/doc/1
{
  "username": "Zobayer11"
}
PUT twitter/doc/2
{
  "username": "Zobayer22"
}
EOF

# create file V1_4__delete_all_doc_in_twitter.exm
cat << EOF > "$dirname/V1_4__delete_all_doc_in_twitter.exm"
POST twitter/_delete_by_query
{
  "query": {
    "match_all": {}
  }
}
EOF

# create file V1_5__delete_index_twitter.exm
cat << EOF > "$dirname/V1_5__delete_index_twitter.exm"
DELETE twitter
EOF

# add them to git
git add $dirname --all
