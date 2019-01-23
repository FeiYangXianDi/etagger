from __future__ import print_function
import sys
import re
import tensorflow as tf
import numpy as np
from embvec import EmbVec

class Input:
    def __init__(self, data, config, build_output=True):
        self.sentence_word_ids = []             # [batch_size, max_sentence_length]
        self.sentence_wordchr_ids = []          # [batch_size, max_sentence_length, word_length]
        if config.emb_class == 'elmo':
            self.sentence_elmo_wordchr_ids = [] # [batch_size, max_sentence_length+2, word_length]
        if config.emb_class == 'bert':
            self.sentence_bert_token_ids = []   # [batch_size, bert_max_seq_length]
            self.sentence_bert_token_masks = [] # [batch_size, bert_max_seq_length]
            self.sentence_bert_segment_ids = [] # [batch_size, bert_max_seq_length]
        self.sentence_pos_ids = []              # [batch_size, max_sentence_length]
        if build_output:
            self.sentence_tags = []             # [batch_size, max_sentence_length, class_size] 
        self.config = config

        # compute max sentence length
        if type(data) is list:
            self.max_sentence_length = len(data)
        else: # treat as file path
            self.max_sentence_length = self.find_max_length(data)

        if type(data) is list: # treat data as bucket
            bucket = data
            word_ids = self.__create_word_ids(bucket)
            self.sentence_word_ids.append(word_ids)
            wordchr_ids = self.__create_wordchr_ids(bucket)
            self.sentence_wordchr_ids.append(wordchr_ids)
            if config.emb_class == 'elmo':
                elmo_wordchr_ids = self.__create_elmo_wordchr_ids(bucket)
                self.sentence_elmo_wordchr_ids.append(elmo_wordchr_ids)
            if config.emb_class == 'bert':
                bert_token_ids, bert_token_masks, bert_segment_ids = self.__create_bert_input(bucket, 0)
                self.sentence_bert_token_ids.append(bert_token_ids)
                self.sentence_bert_token_masks.append(bert_token_masks)
                self.sentence_bert_segment_ids.append(bert_segment_ids)
            pos_ids = self.__create_pos_ids(bucket)
            self.sentence_pos_ids.append(pos_ids)
            if build_output:
                tag = self.__create_tag(bucket)
                self.sentence_tags.append(tag)
        else:                  # treat data as file path
            path = data
            bucket = []
            ex_index = 0
            for line in open(path):
                if line in ['\n', '\r\n']:
                    word_ids = self.__create_word_ids(bucket)
                    self.sentence_word_ids.append(word_ids)
                    wordchr_ids = self.__create_wordchr_ids(bucket)
                    self.sentence_wordchr_ids.append(wordchr_ids)
                    if config.emb_class == 'elmo':
                        elmo_wordchr_ids = self.__create_elmo_wordchr_ids(bucket)
                        self.sentence_elmo_wordchr_ids.append(elmo_wordchr_ids)
                    if config.emb_class == 'bert':
                        bert_token_ids, bert_token_masks, bert_segment_ids = self.__create_bert_input(bucket, ex_index)
                        self.sentence_bert_token_ids.append(bert_token_ids)
                        self.sentence_bert_token_masks.append(bert_token_masks)
                        self.sentence_bert_segment_ids.append(bert_segment_ids)
                    pos_ids = self.__create_pos_ids(bucket)
                    self.sentence_pos_ids.append(pos_ids)
                    if build_output:
                        tag = self.__create_tag(bucket)
                        self.sentence_tags.append(tag)
                    bucket = []
                    ex_index += 1
                else:
                    bucket.append(line)

    def __create_word_ids(self, bucket):
        """Create an word id vector
        """
        word_ids = []
        sentence_length = 0
        for line in bucket:
            line = line.strip()
            tokens = line.split()
            assert (len(tokens) == 4)
            sentence_length += 1
            word = tokens[0]
            wid = self.config.embvec.get_wid(word)
            word_ids.append(wid)
            if sentence_length == self.max_sentence_length: break
        # padding with pad wid
        for _ in range(self.max_sentence_length - sentence_length):
            word_ids.append(self.config.embvec.pad_wid)
        return word_ids

    def __create_wordchr_ids(self, bucket):
        """Create a vector of a character id vector
        """
        wordchr_ids = []
        sentence_length = 0
        for line in bucket:
            line = line.strip()
            tokens = line.split()
            assert (len(tokens) == 4)
            sentence_length += 1
            chr_ids = []
            word_length = 0
            word = tokens[0]
            for ch in list(word):
                word_length += 1 
                cid = self.config.embvec.get_cid(ch)
                chr_ids.append(cid)
                if word_length == self.config.word_length: break
            # padding with pad cid
            for _ in range(self.config.word_length - word_length):
                chr_ids.append(self.config.embvec.pad_cid)
            wordchr_ids.append(chr_ids)
            if sentence_length == self.max_sentence_length: break
        # padding with [pad_cid, ..., pad_cid] chr_ids
        for _ in range(self.max_sentence_length - sentence_length):
            chr_ids = []
            for _ in range(self.config.word_length):
                chr_ids.append(self.config.embvec.pad_cid)
            wordchr_ids.append(chr_ids)
        return wordchr_ids

    def __create_elmo_wordchr_ids(self, bucket):
        """Create a vector of a character id vector for elmo
        """
        sentence = []
        sentence_length = 0
        for line in bucket:
            line = line.strip()
            tokens = line.split()
            assert (len(tokens) == 4)
            sentence_length += 1
            word = tokens[0]
            sentence.append(word)
            if sentence_length == self.max_sentence_length: break
        elmo_wordchr_ids = self.config.elmo_batcher.batch_sentences([sentence])[0].tolist()
        # padding with [0,...,0] chr_ids, '+2' stands for '<S>, </S>'
        for _ in range(self.max_sentence_length - len(elmo_wordchr_ids) + 2):
            chr_ids = []
            for _ in range(self.config.word_length):
                chr_ids.append(0)
            elmo_wordchr_ids.append(chr_ids)
        assert(len(elmo_wordchr_ids) == self.max_sentence_length+2)
        return elmo_wordchr_ids

    def __create_bert_input(self, bucket, ex_index):
        """Create a vector of token id, token mask, segment id for bert
        """
        bert_tokenizer = self.config.bert_tokenizer
        bert_max_seq_length = self.config.bert_max_seq_length
        bert_tokens = []
        for line in bucket:
            line = line.strip()
            tokens = line.split()
            assert (len(tokens) == 4)
            word = tokens[0]
            bert_token = bert_tokenizer.tokenize(word)
            bert_tokens.extend(bert_token)
        if len(bert_tokens) >= bert_max_seq_length - 1:
           bert_tokens = bert_tokens[0:(bert_max_seq_length - 2)]

        ntokens = []
        segment_ids = []
        ntokens.append("[CLS]")
        segment_ids.append(0)
        for i, token in enumerate(bert_tokens):
            ntokens.append(token)
            segment_ids.append(0)
        ntokens.append("[SEP]")
        segment_ids.append(0)
        token_ids = bert_tokenizer.convert_tokens_to_ids(ntokens)
        token_masks = [1] * len(token_ids)
        # padding
        while len(token_ids) < bert_max_seq_length:
            token_ids.append(0)
            token_masks.append(0)
            segment_ids.append(0)
            ntokens.append("**NULL**")
        assert len(token_ids) == bert_max_seq_length
        assert len(token_masks) == bert_max_seq_length
        assert len(segment_ids) == bert_max_seq_length
        if ex_index < 5:
            from bert import tokenization  
            tf.logging.info("*** Example ***")
            tf.logging.info("tokens: %s" % " ".join([tokenization.printable_text(x) for x in bert_tokens]))
            tf.logging.info("token_ids: %s" % " ".join([str(x) for x in token_ids]))
            tf.logging.info("token_masks: %s" % " ".join([str(x) for x in token_masks]))
            tf.logging.info("segment_ids: %s" % " ".join([str(x) for x in segment_ids]))
        return token_ids, token_masks, segment_ids

    def __create_pos_ids(self, bucket):
        """Create a pos id vector
        """
        pos_ids = []
        sentence_length = 0
        for line in bucket:
            line = line.strip()
            tokens = line.split()
            assert (len(tokens) == 4)
            sentence_length += 1
            pos = tokens[1]
            pid = self.config.embvec.get_pid(pos)
            pos_ids.append(pid)
            if sentence_length == self.max_sentence_length: break
        # padding with pad pid
        for _ in range(self.max_sentence_length - sentence_length):
            pos_ids.append(self.config.embvec.pad_pid)
        return pos_ids

    def __create_tag(self, bucket):
        """Create a vector of an one-hot tag vector
        """
        tag  = []
        sentence_length = 0
        for line in bucket:
            line = line.strip()
            tokens = line.split()
            assert (len(tokens) == 4)
            sentence_length += 1
            tag.append(self.__tag_vec(tokens[3], self.config.class_size))   # tag one-hot(9)
            if sentence_length == self.max_sentence_length: break
        # padding with 0s
        for _ in range(self.max_sentence_length - sentence_length):
            tag.append(np.array([0] * self.config.class_size))
        return tag

    def __tag_vec(self, tag, class_size):
        """Build one-hot for tag
        """
        one_hot = np.zeros(class_size)
        tid = self.config.embvec.get_tid(tag)
        one_hot[tid] = 1
        return one_hot

    def logit_to_tags(self, logit, length):
        """Convert logit to tags

        Args:
          logit: [sentence_length, class_size]
          length: int

        Returns:
          tag sequence(size length)
        """
        logit = logit[0:length]
        # [length]
        pred_list = np.argmax(logit, 1).tolist()
        tags = []
        for tid in pred_list:
            tag = self.config.embvec.get_tag(tid)
            tags.append(tag)
        return tags

    def logit_indices_to_tags(self, logit_indices, length):
        """Convert logit_indices to tags

        Args:
          logit_indices: [sentence_length]
          length: int

        Returns:
          tag sequence(size length)
        """
        pred_list = logit_indices[0:length]
        tags = []
        for tid in pred_list:
            tag = self.config.embvec.get_tag(tid)
            tags.append(tag)
        return tags

    def logits_indices_to_tags_seq(self, logits_indices, lengths):
        """Convert logits_indices to sequence of tags

        Args:
          logits_indices: [batch_size, sentence_length]
          lengths: [batch_size]

        Returns:
          sequence of tags
        """
        tags_seq = []
        for logit_indices, length in zip(logits_indices, lengths):
            tags = self.logit_indices_to_tags(logit_indices, length)
            tags_seq.append(tags)
        return tags_seq

    @staticmethod
    def find_max_length(file_name):
        temp_len = 0
        max_length = 0
        for line in open(file_name):
            if line in ['\n', '\r\n']:
                if temp_len > max_length:
                    max_length = temp_len
                temp_len = 0
            else:
                temp_len += 1
        return max_length
