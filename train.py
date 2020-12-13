import os
import re
import marshal

import tensorflow as tf
import tensorflow_datasets as tfds
import numpy as np
from datetime import datetime
# from tensorflow.keras.utils import plot_model
from concurrent.futures import ThreadPoolExecutor, wait
from tensorboard.plugins import projector
from random import shuffle, randint

config = tf.compat.v1.ConfigProto()
config.gpu_options.allow_growth = True
session = tf.compat.v1.Session(config=config)
os.environ['TF_GPU_THREAD_MODE'] = "gpu_private"

path_to_dataset = "cornell movie-dialogs corpus"

path_to_movie_lines = os.path.join(path_to_dataset, "movie_lines.txt")
path_to_movie_conversations = os.path.join(path_to_dataset, "movie_conversations.txt")

# tf.compat.v1.set_random_seed(1234)
MAX_SAMPLES = int(input("MAX_SAMPLES: "))
name = input("Please enter a ModelName for this train: ")
log_dir = "bunchOfLogs/" + name
BATCH_SIZE = int(input("BATCH_SIZE(32): "))
BUFFER_SIZE = int(input("BUFFER_SIZE(60k): "))
MAX_LENGTH = 80 + 2

# Hyper-parameters
NUM_LAYERS = int(input("Please enter the number of NUM_LAYERS(4): "))
D_MODEL = int(input("Please enter the d_model(256): "))
NUM_HEADS = int(input("Please enter the NUM_HEADS(8): "))
UNITS = int(input("Please enter the number of units(512): "))
DROPOUT = float(input("Please enter the DROPOUT(0.175): "))
EPOCHS = int(input("Please enter the number of epochs(15): "))
load = input("Would you like to load the tokenizer? y/n: ")
tokenizerPath = None
if load == "y":
    tokenizerPath = input("Please enter the path the tokenizer: ")
TARGET_VOCAB_SIZE = 2 ** 14

checkpoint_path = f"{log_dir}/cp.ckpt"
try:
    os.mkdir(f"{log_dir}")
    os.mkdir(f"{log_dir}/model/")
    os.mkdir(f"{log_dir}/pickles/")
    os.mkdir(f"{log_dir}/tokenizer")
    os.mkdir(f"{log_dir}/values/")
except FileExistsError:
    print("Already exists not creating folders")
    pass

reddit_set_max = MAX_SAMPLES
movie_dialog_max = 0
while reddit_set_max > MAX_SAMPLES or None:
    reddit_set_max = int(input("Please enter a valid number\n>"))
if movie_dialog_max > 600000:
    reddit_set_max = int(input("Please enter a valid number. The movie dialog only has 600k samples: "))


# tf.debugging.experimental.enable_dump_debug_info(log_dir, tensor_debug_mode="FULL_HEALTH", circular_buffer_size=-1)


def preprocess_sentence(sentence):
    # creating a space between a word and the punctuation following it
    # eg: "he is a boy." => "he is a boy ."
    sentence = re.sub(r"([?.!,'])", r"\1", sentence)
    sentence = re.sub(r"[^a-zA-Z?.!,']+", " ", sentence)
    # replacing everything with space except (a-z, A-Z, ".", "?", "!", ",")
    sentence = re.sub(r"[^a-zA-z?.!,']+", " ", sentence)
    sentence = sentence.strip()
    # adding start and an end token to the sentence
    return sentence


# noinspection PyShadowingNames,PyPep8Naming
def load_conversations(reddit_set_max, movie_dialog_max):
    id2line = {}
    inputs, outputs = [], []
    if movie_dialog_max > 0:
        with open(path_to_movie_lines, errors="ignore") as file:
            lines = file.readlines()
        for line in lines:
            parts = line.replace('\n', '').split(' +++$+++ ')
            id2line[parts[0]] = parts[4]

        with open(path_to_movie_conversations, 'r') as file:
            lines2 = file.readlines()
        for line2 in lines2:
            parts = line2.replace('\n', '').split(" +++$+++ ")
            # get the conversation in a list of line ID
            conversation = [line2[1:-1] for line2 in parts[3][1:-1].split(', ')]
            for i in range(len(conversation) - 1):
                inputs.append(preprocess_sentence(id2line[conversation[i]]))
                outputs.append(preprocess_sentence(id2line[conversation[i + 1]]))
                if len(inputs) >= movie_dialog_max:
                    break

    with open("train.from", "r", encoding="utf8", buffering=1000) as file:
        newline = " newlinechar "
        for line in file:
            if newline in line:
                line = line.replace(newline, "\n")
            inputs.append(line)
            if len(inputs) >= reddit_set_max / 2:
                break
        file.close()

    with open("train.to", "r", encoding="utf8", buffering=1000) as file:
        newline = " newlinechar "
        for line in file:
            if newline in line:
                line = line.replace(newline, "\n")
            outputs.append(line)
            if len(outputs) >= reddit_set_max / 2:
                file.close()
                return inputs, outputs
        file.close()
    return inputs, outputs


def save_marshal(item, f_path):
    file = open(f_path, 'ab')
    marshal.dump(item, file)
    file.close()


def save_files(item1, item2, file1, file2):
    with ThreadPoolExecutor(2) as executor:
        executor.submit(save_marshal, item1, file1)
        executor.submit(save_marshal, item2, file2)
        wait((executor.submit(save_marshal, item1, file1), executor.submit(save_marshal, item2, file2)))


def generate_data(max_data, f_path):
    num_data = 0
    return_phrases = []
    new_phrases = file_generator(f_path)
    while not num_data >= max_data:
        new_phrase = next(new_phrases)
        phrase = preprocess_sentence(new_phrase)
        if phrase not in return_phrases and not len(return_phrases) >= max_data:
            return_phrases.append(phrase)
            num_data += 1
    return return_phrases


def sort_data(max_data, filepath_one="train.from", filepath_two="train.to"):
    inputs = generate_data(f_path=filepath_one, max_data=max_data)
    outputs = generate_data(f_path=filepath_two, max_data=max_data)
    return inputs, outputs


def file_generator(f_path):
    with open(f_path, "r", encoding="utf8", buffering=10000) as file:
        newline = " newlinechar "
        for line in file:
            if newline in line:
                line = line.replace(newline, "\n")
            yield line


print("Loading files...")
questions, answers = load_conversations(reddit_set_max, movie_dialog_max)
print(f"Data size Answers: {len(answers)}\nQuestions: {len(questions)}")
# questions, answers = sort_data(reddit_set_max)
shuffleThis = list(zip(questions, answers))
for x in range(randint(0, 10)):
    shuffle(shuffleThis)
questions, answers = zip(*shuffleThis)
print("Done loading...")
print(f"Pickling Questions and answers for {name}")
questionsMarshal = f"{log_dir}/pickles/{name}_questions.marshal"
answersMarshal = f"{log_dir}/pickles/{name}_answers.marshal"
save_marshal(questions, questionsMarshal)
save_marshal(answers, answersMarshal)
print(f"Done saving....")
if load == "n":
    print("Starting Tokenizer this may take a while....")
    # Build tokenizer using tfds for both questions and answers
    tokenizer = tfds.features.text.SubwordTextEncoder.build_from_corpus(
        questions + answers, target_vocab_size=TARGET_VOCAB_SIZE)
    tokenizer.save_to_file(f"{log_dir}/tokenizer/vocabTokenizer")
else:
    tokenizer = tfds.features.text.SubwordTextEncoder.load_from_file(tokenizerPath)
    tokenizer.save_to_file(f"{log_dir}/tokenizer/vocabTokenizer")
print("Done Tokenizer.")
# Define start and end token to indicate the start and end of a sentence
START_TOKEN, END_TOKEN = [tokenizer.vocab_size], [tokenizer.vocab_size + 1]

# Vocabulary size plus start and end token
VOCAB_SIZE = tokenizer.vocab_size + 2

'''
# Tokenize, filter and pad sentences
def tokenize_and_filter(inputs, outputs):
    tokenized_inputs, tokenized_outputs = [], []
    max_len = MAX_LENGTH - (len(START_TOKEN) - len(END_TOKEN))
    for (sentence1, sentence2) in zip(inputs, outputs):
        # Check tokenized max length
        if len(sentence1) <= max_len and len(sentence2) <= max_len:
            # tokenize sentence
            sentence1 = START_TOKEN + tokenizer.encode(sentence1) + END_TOKEN
            sentence2 = START_TOKEN + tokenizer.encode(sentence2) + END_TOKEN
            tokenized_inputs.append(sentence1)
            tokenized_outputs.append(sentence2)

    print("Done filtering")
    print("Padding")

    # pad tokenized sentences
    tokenized_inputs = tf.keras.preprocessing.sequence.pad_sequences(tokenized_inputs, maxlen=max_len,
                                                                     padding='post')
    tokenized_outputs = tf.keras.preprocessing.sequence.pad_sequences(tokenized_outputs, maxlen=max_len,
                                                                      padding='post')
    print("Done padding")
    return tokenized_inputs, tokenized_outputs
'''


def tokenize_and_filter(inputs, outputs):
    # Get rid of any inputs/outputs that don't meet the max_length requirement (save the model training on large sentences
    new_inputs, new_outputs = [], []
    for i, (sentence1, sentence2) in enumerate(zip(inputs, outputs)):
        if len(sentence1) <= MAX_LENGTH - 2 and len(sentence2) <= MAX_LENGTH -2 :
            new_inputs.append(sentence1)
            new_outputs.append(sentence2)
    inputs, outputs = new_inputs, new_outputs

    # Init the shapes for the array.
    shape_inputs = (len(inputs), MAX_LENGTH)
    shape_outputs = (len(outputs), MAX_LENGTH)
    # create the empty numpy arrays
    # Add the start token at the start of all rows
    inputs_array = np.zeros(shape=shape_inputs)
    inputs_array[:, 0] = START_TOKEN[0]
    outputs_array = np.zeros(shape=shape_outputs)
    outputs_array[:, 0] = START_TOKEN[0]
    # Iterate over each sentence in both inputs and outputs.
    for i, (sentence1, sentence2) in enumerate(zip(inputs, outputs)):
        # encode both sentences
        tokenized_sentence1 = tokenizer.encode(sentence1)
        tokenized_sentence2 = tokenizer.encode(sentence2)
        # This check length doesn't technically matter but its here as a fail safe.
        if len(tokenized_sentence1) <= MAX_LENGTH -2 and len(tokenized_sentence2) <= MAX_LENGTH -2:
            # Add the tokenized sentence into array.
            # This acts as padding for hte
            inputs_array[i, 1:len(tokenized_sentence1)+1] = tokenized_sentence1
            inputs_array[i, len(tokenized_sentence1)+1] = END_TOKEN[0]

            outputs_array[i, 1:len(tokenized_sentence2)+1] = tokenized_sentence2
            inputs_array[i, len(tokenized_sentence2)+1] = END_TOKEN[0]

    return inputs_array, outputs_array


print("Filtering data")
questions, answers = tokenize_and_filter(questions, answers)
print("Done filtering")
questions_train = questions[int(round(len(questions) * .8, 0)):]
answers_train = answers[int(round(len(answers) * 0.8, 0)):]
questions_val = questions[:int(round(len(questions) * .2, 0))]
answers_val = answers[:int(round(len(answers) * .2, 0))]

# decoder inputs use the previous target as input
# remove s_token from targets
print("Beginning Dataset shuffling, batching and prefetch")
dataset_train = tf.data.Dataset.from_tensor_slices((
    {
        'inputs': questions_train,
        'dec_inputs': answers_train[:, :-1]
    },
    {
        'outputs': answers_train[:, 1:]
    }
))
dataset_val = tf.data.Dataset.from_tensor_slices((
    {
        'inputs': questions_val,
        'dec_inputs': answers_val[:, :-1]
    },
    {
        'outputs': answers_val[:, 1:]
    }
))
dataset_train = dataset_train.cache()
dataset_train = dataset_train.shuffle(BUFFER_SIZE)
dataset_train = dataset_train.batch(BATCH_SIZE)
dataset_train = dataset_train.prefetch(tf.data.experimental.AUTOTUNE)
dataset_val = dataset_val.cache()
dataset_val = dataset_val.shuffle(BUFFER_SIZE)
dataset_val = dataset_val.batch(BATCH_SIZE)
dataset_val = dataset_val.prefetch(tf.data.experimental.AUTOTUNE)
print("Done Dataset shuffling, batching and prefetch")


def scaled_dot_product_attention(query, key, value, mask):
    # Calculate the attention weights
    matmul_qk = tf.matmul(query, key, transpose_b=True)

    # scale matmul_qk
    depth = tf.cast(tf.shape(key)[-1], tf.float32)
    logits = matmul_qk / tf.math.sqrt(depth)

    # add the mask to zero out padding tokens
    if mask is not None:
        logits += (mask * -1e9)

    # softmax is normalized on the last axis (seq_len_k)
    attention_weights = tf.nn.softmax(logits, axis=-1)

    output = tf.matmul(attention_weights, value)

    return output


# noinspection PyMethodOverriding,PyShadowingNames
class MultiHeadAttention(tf.keras.layers.Layer):

    def __init__(self, d_model, num_heads, name="multi_head_attention"):
        super(MultiHeadAttention, self).__init__(name=name)
        self.num_heads = num_heads
        self.d_model = d_model

        assert d_model % self.num_heads == 0

        self.depth = d_model // self.num_heads

        self.query_dense = tf.keras.layers.Dense(units=d_model)
        self.key_dense = tf.keras.layers.Dense(units=d_model)
        self.value_dense = tf.keras.layers.Dense(units=d_model)

        self.dense = tf.keras.layers.Dense(units=d_model)

    def split_heads(self, inputs, batch_size):
        inputs = tf.reshape(
            inputs, shape=(batch_size, -1, self.num_heads, self.depth))
        return tf.transpose(inputs, perm=[0, 2, 1, 3])

    def call(self, inputs):
        query, key, value, mask = inputs['query'], inputs['key'], inputs['value'], inputs['mask']
        batch_size = tf.shape(query)[0]

        # linear layers
        query = self.query_dense(query)
        key = self.key_dense(key)
        value = self.value_dense(value)

        # split heads
        query = self.split_heads(query, batch_size)
        key = self.split_heads(key, batch_size)
        value = self.split_heads(value, batch_size)

        # scaled dot-production attention
        scaled_attention = scaled_dot_product_attention(query, key, value, mask)

        scaled_attention = tf.transpose(scaled_attention, perm=[0, 2, 1, 3])

        # concatenation of heads
        concat_attention = tf.reshape(scaled_attention, (batch_size, -1, self.d_model))

        # final linear layer
        outputs = self.dense(concat_attention)

        return outputs

    def get_config(self):
        cfg = super().get_config()
        return cfg


# noinspection PyShadowingNames
def create_padding_mask(x):
    mask = tf.cast(tf.math.equal(x, 0), tf.float32)
    # batch_size, 1, 1, sequence_length
    return mask[:, tf.newaxis, tf.newaxis, :]


# noinspection PyShadowingNames
def create_look_ahead_mask(x):
    seq_len = tf.shape(x)[1]
    look_ahead_mask = 1 - tf.linalg.band_part(tf.ones((seq_len, seq_len)), -1, 0)
    padding_mask = create_padding_mask(x)
    return tf.maximum(look_ahead_mask, padding_mask)


# noinspection PyMethodOverriding,PyMethodMayBeStatic
class PositionalEncoding(tf.keras.layers.Layer):

    def __init__(self, position, d_model):
        super(PositionalEncoding, self).__init__()
        self.pos_encoding = self.positional_encoding(position, d_model=d_model)

    def get_angles(self, position, i, d_model):
        angles = 1 / tf.pow(tf.cast(10000, tf.float32), (2 * (i // 2)) / tf.cast(d_model, tf.float32))
        return position * angles

    def positional_encoding(self, position, d_model):
        angle_rads = self.get_angles(
            position=tf.range(position, dtype=tf.float32)[:, tf.newaxis],
            i=tf.range(d_model, dtype=tf.float32)[tf.newaxis, :], d_model=d_model)

        # apply sin to even index in the array
        sines = tf.math.sin(angle_rads[:, 0::2])
        # apply cos to odd index in the array
        cosines = tf.math.cos(angle_rads[:, 1::2])

        pos_encoding = tf.concat([sines, cosines], axis=-1)
        pos_encoding = pos_encoding[tf.newaxis, ...]
        return tf.cast(pos_encoding, tf.float32)

    def call(self, inputs):
        return inputs + self.pos_encoding[:, :tf.shape(inputs)[1], :]

    def get_config(self):
        cfg = super().get_config()
        return cfg


# noinspection PyTypeChecker,PyShadowingNames
def encoding_layer(units, d_model, num_heads, dropout, name="encoder_layer"):
    inputs = tf.keras.Input(shape=(None, d_model), name="inputs")
    padding_mask = tf.keras.Input(shape=(1, 1, None), name="padding_mask")

    attention = MultiHeadAttention(d_model, num_heads, name="attention")({
        'query': inputs,
        'key': inputs,
        'value': inputs,
        'mask': padding_mask
    })
    attention = tf.keras.layers.Dropout(rate=dropout)(attention)
    attention = tf.keras.layers.LayerNormalization(epsilon=1e-6)(inputs + attention)

    outputs = tf.keras.layers.Dense(units=units, activation='relu')(attention)
    outputs = tf.keras.layers.Dense(units=d_model)(outputs)
    outputs = tf.keras.layers.Dropout(rate=dropout)(outputs)
    outputs = tf.keras.layers.LayerNormalization(epsilon=1e-6)(attention + outputs)

    return tf.keras.Model(inputs=[inputs, padding_mask], outputs=outputs, name=name)


# noinspection PyTypeChecker,PyShadowingNames
def encoder(vocab_size, num_layers, units, d_model, num_heads, dropout, name='encoder'):
    inputs = tf.keras.Input(shape=(None,), name='inputs')
    padding_mask = tf.keras.Input(shape=(1, 1, None), name="padding_mask")
    embeddings = tf.keras.layers.Embedding(vocab_size, d_model)(inputs)
    embeddings *= tf.math.sqrt(tf.cast(d_model, tf.float32))
    embeddings = PositionalEncoding(vocab_size, d_model=d_model)(embeddings)

    outputs = tf.keras.layers.Dropout(rate=dropout)(embeddings)

    for i in range(num_layers):
        outputs = encoding_layer(
            units=units,
            d_model=d_model,
            num_heads=num_heads,
            dropout=dropout,
            name="encoding_layer{}".format(i),
        )([outputs, padding_mask])

    return tf.keras.Model(inputs=[inputs, padding_mask], outputs=outputs, name=name)


# noinspection PyShadowingNames
def decoder_layer(units, d_model, num_heads, dropout, name="decoder_layer"):
    inputs = tf.keras.Input(shape=(None, d_model), name="inputs")
    enc_outputs = tf.keras.Input(shape=(None, d_model), name="encoder_outputs")
    look_ahead_mask = tf.keras.Input(shape=(1, None, None), name="look_ahead_mask")
    padding_mask = tf.keras.Input(shape=(1, 1, None), name="padding_mask")

    attention1 = MultiHeadAttention(d_model, num_heads, name="attention1")(inputs={
        'query': inputs,
        'key': inputs,
        'value': inputs,
        'mask': look_ahead_mask
    })
    attention1 = tf.keras.layers.LayerNormalization(epsilon=1e-6)(attention1 + inputs)

    attention2 = MultiHeadAttention(d_model, num_heads, name="attention2")(inputs={
        'query': attention1,
        'key': enc_outputs,
        'value': enc_outputs,
        'mask': padding_mask
    })
    attention2 = tf.keras.layers.Dropout(rate=dropout)(attention2)
    attention2 = tf.keras.layers.LayerNormalization(epsilon=1e-6)(attention2 + attention1)

    outputs = tf.keras.layers.Dense(units=units, activation='relu')(attention2)
    outputs = tf.keras.layers.Dense(units=d_model)(outputs)
    outputs = tf.keras.layers.Dropout(rate=dropout)(outputs)
    outputs = tf.keras.layers.LayerNormalization(epsilon=1e-6)(outputs + attention2)

    return tf.keras.Model(inputs=[inputs, enc_outputs, look_ahead_mask, padding_mask], outputs=outputs, name=name)


# noinspection PyShadowingNames
def decoder(vocab_size,
            num_layers,
            units,
            d_model,
            num_heads,
            dropout,
            name='decoder'):
    inputs = tf.keras.Input(shape=(None,), name='inputs')
    enc_outputs = tf.keras.Input(shape=(None, d_model), name='encoder_outputs')
    look_ahead_mask = tf.keras.Input(shape=(1, None, None), name='look_ahead_mask')
    padding_mask = tf.keras.Input(shape=(1, 1, None), name="padding_mask")

    embeddings = tf.keras.layers.Embedding(vocab_size, d_model)(inputs)
    embeddings *= tf.math.sqrt(tf.cast(d_model, tf.float32))
    embeddings = PositionalEncoding(vocab_size, d_model=d_model)(embeddings)

    outputs = tf.keras.layers.Dropout(rate=dropout)(embeddings)

    for i in range(num_layers):
        outputs = decoder_layer(
            units=units,
            d_model=d_model,
            num_heads=num_heads,
            dropout=dropout,
            name='decoder_layer_{}'.format(i)
        )(inputs=[outputs, enc_outputs, look_ahead_mask, padding_mask])
    return tf.keras.Model(inputs=[inputs, enc_outputs, look_ahead_mask, padding_mask], outputs=outputs, name=name)


# noinspection PyShadowingNames
def transformer(vocab_size,
                num_layers,
                units,
                d_model,
                num_heads,
                dropout,
                name="transformer"):
    inputs = tf.keras.Input(shape=(None,), name="inputs")
    dec_inputs = tf.keras.Input(shape=(None,), name="dec_inputs")

    enc_padding_mask = tf.keras.layers.Lambda(create_padding_mask, output_shape=(1, 1, None),
                                              name="enc_padding_mask")(inputs)
    # mask the future tokens for decoder inputs at the 1st attention block
    look_ahead_mask = tf.keras.layers.Lambda(create_look_ahead_mask, output_shape=(1, None, None),
                                             name="look_ahead_mask")(dec_inputs)

    # mask the encoder outputs for the 2nd attention block
    dec_padding_mask = tf.keras.layers.Lambda(create_padding_mask, output_shape=(1, 1, None), name='dec_padding_mask')(
        inputs)

    enc_outputs = encoder(
        vocab_size=vocab_size,
        num_layers=num_layers,
        units=units,
        d_model=d_model,
        num_heads=num_heads,
        dropout=dropout
    )(inputs=[inputs, enc_padding_mask])

    dec_outputs = decoder(
        vocab_size=vocab_size,
        num_layers=num_layers,
        units=units,
        d_model=d_model,
        num_heads=num_heads,
        dropout=dropout
    )(inputs=[dec_inputs, enc_outputs, look_ahead_mask, dec_padding_mask])

    outputs = tf.keras.layers.Dense(units=vocab_size, name="outputs")(dec_outputs)

    return tf.keras.Model(inputs=[inputs, dec_inputs], outputs=outputs, name=name)


mirrored_strategy = tf.distribute.MirroredStrategy()

with mirrored_strategy.scope():
    model = transformer(
        vocab_size=VOCAB_SIZE,
        num_layers=NUM_LAYERS,
        units=UNITS,
        d_model=D_MODEL,
        num_heads=NUM_HEADS,
        dropout=DROPOUT)


def loss_function(y_true, y_pred):
    y_true = tf.reshape(y_true, shape=(-1, MAX_LENGTH - 1))

    loss = tf.keras.losses.SparseCategoricalCrossentropy(from_logits=True,
                                                         reduction='none')(y_true, y_pred)
    mask = tf.cast(tf.not_equal(y_true, 0), tf.float32)
    loss = tf.multiply(loss, mask)

    return tf.reduce_mean(loss)


def evaluate(sentence):
    sentence = preprocess_sentence(sentence)

    sentence = tf.expand_dims(START_TOKEN + tokenizer.encode(sentence) + END_TOKEN, axis=0)

    output = tf.expand_dims(START_TOKEN, 0)

    for i in range(MAX_LENGTH):
        predictions = model(inputs=[sentence, output], training=False)

        # select the last word from the seq length dimension
        predictions = predictions[:, -1:, :]
        predicted_id = tf.cast(tf.argmax(predictions, axis=-1), tf.int32)

        if tf.equal(predicted_id, END_TOKEN[0]):
            break

        # concatenated the predicted_id to the output which is given the decoder
        # as its input
        output = tf.concat([output, predicted_id], axis=-1)
    return tf.squeeze(output, axis=0)


def predict(sentence):
    prediction = evaluate(sentence)

    predicated_sentence = tokenizer.decode([i for i in prediction if i < tokenizer.vocab_size])

    print("Input: {}".format(sentence))
    print("Output: {}".format(predicated_sentence))

    return predicated_sentence


# noinspection PyAbstractClass,PyShadowingNames
class CustomSchedule(tf.keras.optimizers.schedules.LearningRateSchedule):

    def __init__(self, d_model, warmup_steps=4000):
        super(CustomSchedule, self).__init__()

        self.d_model = d_model
        self.d_model = tf.cast(self.d_model, tf.float32)

        self.warmup_steps = warmup_steps

    def __call__(self, step):
        arg1 = tf.math.rsqrt(step)
        arg2 = step * (self.warmup_steps ** -1.5)

        return tf.math.rsqrt(self.d_model) * tf.math.minimum(arg1, arg2)

    def get_config(self):
        config = {
            'd_model': self.d_model,
            'warmup_steps': self.warmup_steps
        }
        return config


learning_rate = CustomSchedule(D_MODEL)

optimizer = tf.keras.optimizers.Adam(learning_rate, beta_1=0.9, beta_2=0.98, epsilon=1e-9)


def accuracy(y_true, y_pred):
    # ensure labels have shape (batch_size, max_len - 1)
    y_true = tf.reshape(y_true, shape=(-1, MAX_LENGTH - 1))
    return tf.keras.metrics.sparse_categorical_accuracy(y_true, y_pred)


with open(os.path.join(log_dir, 'metadata.tsv'), "w", encoding="utf-8") as f:
    for subwords in tokenizer.subwords:
        f.write(f"{subwords}\n")
    for unknown in range(1, tokenizer.vocab_size - len(tokenizer.subwords)):
        f.write(f"unknown #{unknown}\n")

projector_config = projector.ProjectorConfig()
embedding = projector_config.embeddings.add()

embedding.metadata_path = 'metadata.tsv'
projector.visualize_embeddings(log_dir, projector_config)

linebreak = "--------------------------------"
log = f"""\nDate: {datetime.now().strftime("%d/%m/%Y %H-%M-%S")},
 Name: {name},
 PATH: {checkpoint_path},
 LogDir: {log_dir},
 Image_Path: {log_dir}/images/combined_{name}.png,
 EPOCHS: {EPOCHS}
 MAX_SAMPLES: {MAX_SAMPLES},
 MAX_LENGTH: {MAX_LENGTH},
 NUM_LAYERS: {NUM_LAYERS},
 D_MODEL: {D_MODEL},
 NUM_HEADS: {NUM_HEADS},
 UNITS: {UNITS},
 DROPOUT: {DROPOUT},
 BATCH_SIZE: {BATCH_SIZE},
 BUFFER_SIZE: {BUFFER_SIZE},
 VOCAB_SIZE: {VOCAB_SIZE},
{linebreak}"""
with open("Parameters.txt", "a") as f:
    f.write(log)
with open(f"{log_dir}/values/hparams.txt", "w", encoding="utf8") as f:
    data = f"""{str(MAX_SAMPLES)}
{name}
{str(MAX_LENGTH)}
{str(BATCH_SIZE)}
{str(BUFFER_SIZE)}
{str(NUM_LAYERS)}
{str(D_MODEL)}
{str(NUM_HEADS)}
{str(UNITS)}
{str(DROPOUT)}
{str(VOCAB_SIZE)}
{str(TARGET_VOCAB_SIZE)}
"""
    f.write(data)
    f.close()

# plot_model(model, f"{log_dir}/images/combined_{ModelName}.png", expand_nested=True, show_shapes=True)
cp_callback = tf.keras.callbacks.ModelCheckpoint(filepath=checkpoint_path, save_weights_only=True, verbose=1)
tensorboard_callback = tf.keras.callbacks.TensorBoard(log_dir=log_dir, histogram_freq=1, profile_batch="510, 520",
                                                      update_freq='epoch')

# tf.compat.v1.keras.backend.set_session(tf_debug.TensorBoardDebugWrapperSession(session, "DESKTOP-A17GHDN:8081"))
model.compile(optimizer=optimizer, loss=loss_function, metrics=['accuracy'])
with tf.profiler.experimental.Trace("Train"):
    model.fit(dataset_train, validation_data=dataset_val, epochs=EPOCHS, callbacks=[cp_callback, tensorboard_callback])
print(log)
print(linebreak)
model.summary()
