import os
import sqlite3
import re
import pandas as pd

from multiprocessing import Pool
from collections import Iterable
from random import shuffle
import glob


timeframes = glob.glob("D:/Datasets/reddit_data/databases/*.db")
timeframes = [os.path.basename(timeframe) for timeframe in timeframes]
shuffle(timeframes)  # Shuffle the order in which the time frames are processed


def preprocess_sentence(sentence):
    sentence = sentence.strip()
    # creating a space between a word and the punctuation following it
    # eg: "he is a boy." => "he is a boy ."
    sentence = re.sub(r"([?.!,'*\"])", r" \1 ", sentence)
    # replacing everything with space except (a-z, A-Z, ".", "?", "!", ",", "'")
    sentence = re.sub(r"[^a-zA-z?.!,'*\"]+", " ", sentence)
    sentence = sentence.strip()
    # adding start and an end token to the sentence
    return sentence


def chunk(lst, count):  # Make a list into N number of lists
    size = len(lst) // count  # figure out the size of them all
    for i in range(0, count):
        s = slice(i * size, None if i == count - 1 else (i + 1) * size)  # Using slice here because you can't store 2:3 as a variable
        yield lst[s]  # Yield the list


def preprocess_process(sentences):
    outputs = []
    for sentence in sentences:
        outputs.append(preprocess_sentence(sentence))
    return outputs


def flatten(lis):
    for item in lis:
        if isinstance(item, Iterable) and not isinstance(item, str):
            for i in flatten(item):
                yield i
        else:
            yield item


def sort_out(time_frame):
    for t_frame in time_frame:
        connection = sqlite3.connect('D:/Datasets/reddit_data/databases/{}'.format(t_frame))
        limit = 1000000
        last_unix = 0
        cur_length = limit
        inputs = []
        outputs = []
        count = 0
        cores = os.cpu_count()
        write_inputs = []
        write_outputs = []

        while cur_length == limit:
            try:
                df = pd.read_sql(
                    "SELECT * FROM parent_reply WHERE unix > {} and parent NOT NULL and score > 0 ORDER BY unix ASC LIMIT {}".format(
                        last_unix, limit), connection)
            except Exception as e:
                print(f"Timeframe: {t_frame} Error: {e}")
            else:
                last_unix = df.tail(1)['unix'].values[0]
                cur_length = len(df)
                for content in df['parent'].values:
                    inputs.append(preprocess_sentence(str(content)))

                for content in df['comment'].values:
                    outputs.append(preprocess_sentence(str(content)))

                generator_i = chunk(df['parent'].values, cores)
                generator_o = chunk(df['comment'].values, cores)
                lists_i = [next(generator_i) for _ in range(cores)]
                lists_o = [next(generator_o) for _ in range(cores)]
                p = Pool(cores)
                process_outputs = p.map(preprocess_process, lists_i)
                p.close()

                write_inputs.extend(list(flatten(process_outputs)))

                p = Pool(cores)
                process_outputs = p.map(preprocess_process, lists_o)
                p.close()

                write_outputs.extend(list(flatten(process_outputs)))
                count += 1
                if count % 10 == 0:
                    print(f"{count * limit} rows down so far.")

            with open("D:\\Datasets\\reddit_data\\files\\train.from", "a", encoding='utf8') as f:
                for sentence in write_inputs:
                    f.write(sentence + '\n')

            with open("D:\\Datasets\\reddit_data\\files\\train.to", "a", encoding='utf-8') as f:
                for sentence in write_outputs:
                    f.write(sentence + '\n')
        print(f"{t_frame} finished.")


if __name__ == "__main__":
    sort_out(timeframes)
