#ifndef CONFIG_H
#define CONFIG_H

class Config {
  
  public:
    Config();
    Config(int word_length, bool use_crf);
    int  GetChrDim() { return chr_dim; }
    int  GetPosDim() { return pos_dim; }
    int  GetEtcDim() { return etc_dim; }
    void SetClassSize(int class_size) { this->class_size = class_size; }
    int  GetClassSize()  { return class_size; }
    int  GetWordLength() { return word_length; }
    bool GetUseCRF() { return use_crf; }
    ~Config();
  
  private:
    // same as config.py
    int chr_dim = 50;
    int pos_dim = 6;
    int etc_dim = 9;
    int class_size;     // assigned after loading vocab
    int word_length;
    bool use_crf;
};

#endif
