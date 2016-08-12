# phlaml

Yaml test flow runner

## Usage

Run commands phlaml <file>.  Inspired by CircleCi's circle.yaml files.

## Format

phlaml expects a yaml file as input, with the top-level being a
"sequence."  

Note that in yaml, a number of symbols require quotation marks:

`{ } [ ] , & * # ? | - < > = ! % @ \)`

## Predicates

Commands can set predicates to control which lines are executed.

For example, you can use a predicate to determine whether you set up 
data in a cache:
```
-  "[ -d ~/cache ]":
    set: cached
- "mkdir -p ~/cache && do-something > ~/cache/file":
    unless: cached
```

## Parallelism

The simplest level of parallelism is to run a script in the
"background".  This can be used to capture examples indefinitely.

```
- "tail -f /var/log":
    background: true
```

Dependencies can be created between background jobs by giving them a
'name'.  Any 'named' are implicitly background processes.

```
- "curl https://host/file1 > file1":
    name: download_file1
- "curl https://host/file2 > file1":
    name: download_file2
- "tail -f /var/log":
    depends_on: download_file1 download_file2
```

Dependencies can be specified as yaml sequences or a single string of
whitespace delimited strings.

## Retries

Commands can be retried a given number of times at a given interval:

```
- "[ -e file ] || { touch file; false; }":
    interval: 5
    retries: 1
```
