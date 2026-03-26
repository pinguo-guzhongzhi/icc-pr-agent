# PR review

本项目主要实现使用大模型对git pr进行review, 可以指定模版输出review结果，要求支持github、gitlab、阿里的codeup

使用langchain的deepagents实现AI review相关功能, 同时需要把review的结果写回github、gitlab、codeup的PR上

## 调用方法 

### shell调用方法
```shell
python pr.py PR链接
```

### api接口

提供api接口接收 github、gitlab、codeup的回调自动触发