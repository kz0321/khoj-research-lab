---
language:
- en
license:
- cc-by-sa-3.0
- gfdl
tags:
- rag
- long-context
- llm-search
- reasoning
- factuality
- retrieval
- question-answering
- iterative-search
task_categories:
- text-classification
- token-classification
- table-question-answering
- question-answering
dataset_info:
  features:
  - name: title
    dtype: string
  - name: link
    dtype: string
  - name: frames_prompt_id
    sequence: int64
  - name: original_link
    sequence: string
  - name: text
    dtype: string
  splits:
  - name: train
    num_bytes: 57344587
    num_examples: 2524
  download_size: 33251945
  dataset_size: 57344587
configs:
- config_name: default
  data_files:
  - split: train
    path: data/train-*
---

# FRAMES Wikipedia Articles

This dataset contains fulltext of Wikipeida articles used in [FRAMES benchmark](https://huggingface.co/datasets/google/frames-benchmark) [(https://arxiv.org/abs/2409.12941)](https://arxiv.org/abs/2409.12941) for testing the capabilities of Retrieval-Augmented Generation (RAG) systems across factuality, retrieval accuracy, and reasoning.

The articles are retrieved in Oct. 2024.