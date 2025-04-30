# README

### 介绍

用户可通过自主编写evaluate.py文件，实现打分逻辑，并重新打包为zip，评测配置页面。当测试记录可成功出分时，此时该条测试记录的状态会显示”成功“字样，“发布”按钮也会变成可点击状态。点击“发布”该条测试记录状态会显示为“审核中”字样，待天池工作人员审核通过即可完成评测程序发布上线。

### 编写一个评测的步骤

注意评测系统的python版本为3.9.12，所以需要使用python 3的语法格式。

1.  下载 评测程序.zip；
    
2.  解压评测程序.zip 得到eval.zip，等一些评测文件；
    
3.  修改evaluate.py，完善评测逻辑，以及错误时的错误描述逻辑；
    
4.  在eval文件夹下放入标准答案和测试提交文件，例如answer.txt、submit.txt(具体文件后缀名视赛题需要可自行设定)
    
5.  填写input\_param.json标准答案和测试提交文件，例如：
    
    {
      "fileData":{
        "evaluatorDir":"",
        "evaluatorPath":"",
        "standardFileDir":"",
        "standardFilePath":"answer.txt",
        "userFileDir":"",
        "userFilePath":"submit.txt"
      }
    }
    
1.  如有特殊的包需要额外安装，请在评测配置页面requirements输入框中进行填写，每个包名称后需进行换行。
    
2.  本地测试评测程序，运行结束查看eval\_result.json结果是否正常：
    

    python3 evaluate.py input_param.json eval_result.json

1.  重新打包为压缩包，必须包含修改后的evaluate.py打分逻辑文件和启动文件py\_entrance.sh(无须修改demo中的py\_entrance.sh)，文件树状结构如下所示：
    

——eval.zip

——evaluate.py

——py\_entrance.sh

——...（其他包含中间过程函数的python文件）

2.  将评测程序、参考输入和标准答案在天池大赛系统的评测配置页面进行提交即可完成一次测试。如果测试记录状态为“成功”可点击“发布”按钮提交审核；如果测试失败，请根据测试记录提供的错误信息和详情对打分逻辑代码进行修改。
    

### 打分代码介绍

#### 1.输入和输出参数

当选手提交了结果文件或者选手代码预测生成了结果文件后，天池平台的打分服务，会这样触发调用：

    sh py_entrance.sh input_param.json eval_result.json

其中第一个参数input\_param.json文件，用于在打分逻辑代码中读取评测标准答案和选手提交文件，内容示例如下（**该文件请勿自行增加字段**）：

    {
      "fileData":{
        "evaluatorDir":"",
        "evaluatorPath":"",
        "standardFileDir":"",
        "standardFilePath":"评测答案文件路径，比如answer.zip/the path of ground truth",
        "userFileDir":"",
        "userFilePath":"需要被评测的文件路径，比如submit.zip/ the path of submission"
      }
    }

第二个参数eval\_result.json，表示评测程序应该把结果写入这个文件。

**注意：**

*   以上两个文件仅在本地自测时使用，正式对选手提交文件进行评测时，内容均会动态生成
    
*   打分逻辑程序（evaluate.py）不需要关注具体的名称，直接取值即可：
    

    input_file  = open(sys.argv[1])
    input_param = json.load(input_file)
    
    # 答案文件路径 the path of ground truth
    standard_file = input_param['fileData']['standardFilePath']
    # 用户提交文件路径 the path of submission
    user_file     = input_param['fileData']['userFilePath']
    
*   针对结果文件：
    

    output_file = open(sys.argv[2], 'w')

#### 2.输出结果的规范

*   评测成功的输出：
    
    {
      "score": 1.0,  # 这个score是必须的，请勿删除并改为其他名称
      "scoreJson": {
        "score": 1.0  # 这里的key一般也是score，注意保留这个key；但可以增加其他key，如下示例
      	"score1": 1.5 # 只是示例
      	"score2": 2.0 # 只是示例，注意这里的value不能是[]之类的，必须只是一个分数
      },
      "success": true
    }
    
*   评测错误的输出：
    

    {
      "errorDetail": "user input is wrong, please check !",
      "errorMsg": "user input is wrong, please check !", # 这个会透出给用户
      "score": 0,
      "scoreJson": { # 注意出错时，scoreJson请保持为{}
      },
      "success": false
    }

#### 3.打分程序注意事项

*   需要解压答案和选手文件的情况
    

目前打分程序在容器运行的逻辑是，下载评测代码、标准答案、选手答案，为root用户运行；**解压到当前目录下（标准答案：**./standard/**）（提交文件：./submit/）；****同时针对选手答案的解压，如果发现该目录已经存在，一定要先删除并再解压！**示例代码如下：

    import zipfile
    import os
    import logging
    import shutil
    
    ......
    
    # standard_file 代表标准答案的路径
    if os.path.isdir('./standard') and len(os.listdir('./standard')) > 0:
      	logging.info("no need to unzip %s", standard_file)
    else:
        with zipfile.ZipFile(standard_file, "r") as zip_ref:
            zip_ref.extractall("./standard")
            zip_ref.close()
    
    # submit_file 表示选手提交的文件路径
    submit_file_dir = os.path.join("./submit/")
    if os.path.isdir(submit_file_dir):
        shutil.rmtree(submit_file_dir)
    with zipfile.ZipFile(submit_file, "r") as zip_data:
        zip_data.extractall(submit_file_dir)
        zip_data.close()

*   请注意需要多次测试评测程序，以保证能涵盖选手提交情况进而给出选手适当的错误信息。测试情况包括但不限于：提交格式不符合要求；提交条数有缺失；重复数据提交数据有0，Null，空格；评测指标存在分母为0的情况；使用log时注意检查负数；提交全错数据；提交全对数据；提交正常答案。
    



### 评测运行环境已安装的python包列表

Package              Version     Editable project location
-------------------- ----------- ----------------------------
aiohappyeyeballs     2.6.1
aiohttp              3.11.16
aiosignal            1.3.2
annotated-types      0.7.0
anyio                4.9.0
argon2-cffi          23.1.0
argon2-cffi-bindings 21.2.0
asn1crypto           1.5.1
async-timeout        5.0.1
attrs                25.3.0
azure-core           1.33.0
azure-storage-blob   12.25.1
certifi              2023.11.17
cffi                 1.17.1
charset-normalizer   3.4.1
click                8.1.8
colorama             0.4.6
cryptography         44.0.2
datasets             2.19.1
dill                 0.3.8
elasticsearch        7.11.0
environs             9.5.0
et_xmlfile           2.0.0
exceptiongroup       1.2.2
fastapi              0.109.2
filelock             3.18.0
frozenlist           1.5.0
fsspec               2024.3.1
grpcio               1.60.0
h11                  0.14.0
huggingface-hub      0.30.2
idna                 3.10
isodate              0.7.2
jieba                0.42.1
jiojio               1.2.7
jionlp               1.5.20
joblib               1.4.2
jsonlines            4.0.0
loguru               0.7.3
marshmallow          3.26.1
minio                7.2.15
modelscope           1.25.0
multidict            6.4.3
multiprocess         0.70.16
nest-asyncio         1.5.6
nltk                 3.8.1
numpy                1.24.4
omegaconf            2.0.6
openpyxl             3.1.5
oscrypto             1.3.0
packaging            24.2
pandas               2.0.3
pillow               11.1.0
pip                  25.0
propcache            0.3.1
protobuf             6.30.2
pyarrow              19.0.1
pyarrow-hotfix       0.6
pycparser            2.22
pycryptodome         3.22.0
pydantic             2.5.3
pydantic_core        2.14.6
pymilvus             2.3.8
python-dateutil      2.9.0.post0
python-dotenv        1.1.0
python-multipart     0.0.20
pytz                 2025.2
PyYAML               6.0.2
regex                2024.11.6
requests             2.31.0
safetensors          0.5.3
scikit-learn         1.6.1
scipy                1.15.2
setuptools           78.1.0
simplejson           3.19.3
six                  1.17.0
sniffio              1.3.1
starlette            0.36.3
text2vec             1.2.9
threadpoolctl        3.6.0
tokenizers           0.21.1
tqdm                 4.66.6
transformers         4.51.3
typing_extensions    4.13.2
tzdata               2025.2
ujson                5.10.0
urllib3              1.26.20
uvicorn              0.34.1
wheel                0.45.1
win32_setctime       1.2.0
xxhash               3.5.0
yarl                 1.19.0 
zipfile36            0.1.3
