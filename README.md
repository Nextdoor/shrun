# shrun

[![CircleCI](https://circleci.com/gh/Nextdoor/shrun.svg?style=svg)](https://circleci.com/gh/Nextdoor/shrun)

Yaml test flow runner

## Usage

Run commands shrun <file>.  Inspired by CircleCi's circle.yml files.

## Format

shrun expects a yaml file as input, with the top-level being a
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

## Series

Commands can be run for each member in a series:

```
- touch file_{{A,B}}
```

Series can be used in names:


```
- sleep 10; touch file_{{A,B}}:
    name: name_{{A,B}}
- echo Done:
    depends_on: name_A name_B
```

Identical series are replicated together, so

```
- touch file_{{A,B}}; mv file_{{A,B}} dir
```

becomes

```
- touch file_A; mv file_A dir
- touch file_B; mv file_B dir
```

Series can be labeled to avoid having to repeat the content of the group:

Identical groups are replicated together, so

```
- touch file_{{my_series=A,B}}; mv file_{{my_series}} dir
```

also becomes

```
- touch file_A; mv file_A dir
- touch file_B; mv file_B dir
```

Labeled series can be mapped to different values using a 1-1 mapping:

```
- mv file_{{my_series:A,B}} dir{{my_series:1,2}}
```

## Repeated Sequences

Sequences of commands can be repeated for each item in a series.  The first item
 in the sequence must have the 'foreach' property set to a valid series specification.
 
```
- - foreach: my_series=A,B
  - touch file1_{{my_series}}
  - cp file1_{{my_series}} file2_{{my_series}}
```

Sequences can be nested:
 
```
- - foreach: my_series=A,B
  - - foreach: 1,2 
    - touch file1_{{my_series}}_{1,2}
```
