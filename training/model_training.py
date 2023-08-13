from urllib import request

import pandas as pd

from sklearn.model_selection import train_test_split
from sklearn.metrics import f1_score, balanced_accuracy_score, accuracy_score
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline

import mlflow
from prefect import flow, task

from lemma_tokenizer import LemmaTokenizer

mlflow.set_experiment("Test")


@task
def download_dataset(path):
    file_id = '13XlJ4uhxxGprn6mnXwXNvV9PxSNyZCsY'
    url = f'https://drive.google.com/uc?export=download&id={file_id}'
    request.urlretrieve(url, path)


@task
def read_dataset(path):
    def read_lines(lines):
        is_header = True
        for line in lines:
            if is_header:
                is_header = False
                continue

            if not line or line.isspace():
                is_header = True
                continue

            label, comment = line.split(maxsplit=1)
            yield comment, int(label)

    with open(path, 'r') as file:
        data = read_lines(file)
        df = pd.DataFrame.from_records(data, columns=['text', 'label'])

    return df


def fetch_data():
    path = 'dataset.txt'
    download_dataset(path)

    return read_dataset(path)


@task
def clean_data(df):
    return df.drop_duplicates(ignore_index=True)


@task
def split_data(df, test_size):
    X_raw, y = df['text'], df['label']
    X_train, X_test, y_train, y_test = train_test_split(
        X_raw.values, y.values, test_size=test_size, stratify=y, random_state=0)
    X_train, X_test = X_train.flatten(), X_test.flatten()
    return X_train, X_test, y_train, y_test



@flow(log_prints=True)
def train():
    mlflow.sklearn.autolog()

    df = fetch_data()
    df = clean_data(df)

    test_size = 0.1
    X_train, X_test, y_train, y_test = split_data(df, test_size)

    with mlflow.start_run() as run:
        mlflow.log_param('test_size', test_size)

        vectorizer = CountVectorizer(
            tokenizer=LemmaTokenizer(),
            strip_accents='unicode',
            ngram_range=(1, 2),
            min_df=0.0005,
            max_df=0.8)

        clf = MultinomialNB()

        pipeline = Pipeline([('vectorizer', vectorizer), ('clf', clf)])
        
        print('Model training')
        pipeline.fit(X_train, y_train)
        
        print('Model evaluation')
        pipeline.score(X_test, y_test)
        y_pred_test = pipeline.predict(X_test)
        
        f1 = f1_score(y_test, y_pred_test, average='macro')
        balanced_accuracy_score(y_test, y_pred_test)
        accuracy_score(y_test, y_pred_test)

        num_features_basic = vectorizer.transform(X_test).shape[1]
        mlflow.log_param('num_features_basic', num_features_basic)

    print(f"Logged data and model in run: {run.info.run_id}")

    if f1 >= 0.7:
        model_uri = f"runs:/{run.info.run_id}/model"
        mv = mlflow.register_model(model_uri, "MultinomialNB")
        print(f"Name: {mv.name}")
        print(f"Version: {mv.version}")
        
    else:
        print(f'Model registration failed, f1 score too low (< 0.7)')


if __name__ == "__main__":
    train()
