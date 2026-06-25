# SpringBoot集成Kafka

> 来源: https://liaoxuefeng.com/books/java/springboot/integration/kafka/index.html
> 爬取时间: 2026-06-25 13:29:56
> 学科: software_eng | 难度: 进阶
> 标签: SpringBoot, Kafka, 消息队列, 集成, 进阶

---


### Java教程


# 集成Kafka


我们在前面已经介绍了JMS和AMQP，JMS是JavaEE的标准消息接口，Artemis是一个JMS实现产品，AMQP是跨语言的一个标准消息接口，RabbitMQ是一个AMQP实现产品。


Kafka也是一个消息服务器，它的特点一是快，二是有巨大的吞吐量，那么Kafka实现了什么标准消息接口呢？


Kafka没有实现任何标准的消息接口，它自己提供的API就是Kafka的接口。


哥没有实现任何标准，哥自己就是标准。


—— Kafka


Kafka本身是Scala编写的，运行在JVM之上。Producer和Consumer都通过Kafka的客户端使用网络来与之通信。从逻辑上讲，Kafka设计非常简单，它只有一种类似JMS的Topic的消息通道：


```
┌──────────┐
                       ┌──▶│Consumer-1│
                       │   └──────────┘
┌────────┐    ┌─────┐  │   ┌──────────┐
│Producer│───▶│Topic│──┼──▶│Consumer-2│
└────────┘    └─────┘  │   └──────────┘
                       │   ┌──────────┐
                       └──▶│Consumer-3│
                           └──────────┘
```


那么Kafka如何支持十万甚至百万的并发呢？答案是分区。Kafka的一个Topic可以有一个至多个Partition，并且可以分布到多台机器上：


```
┌ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐
             Topic
            │                   │
                ┌───────────┐        ┌──────────┐
            │┌─▶│Partition-1│──┐│┌──▶│Consumer-1│
             │  └───────────┘  │ │   └──────────┘
┌────────┐  ││  ┌───────────┐  │││   ┌──────────┐
│Producer│───┼─▶│Partition-2│──┼─┼──▶│Consumer-2│
└────────┘  ││  └───────────┘  │││   └──────────┘
             │  ┌───────────┐  │ │   ┌──────────┐
            │└─▶│Partition-3│──┘│└──▶│Consumer-3│
                └───────────┘        └──────────┘
            └ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘
```


Kafka只保证在一个Partition内部，消息是有序的，但是，存在多个Partition的情况下，Producer发送的3个消息会依次发送到Partition-1、Partition-2和Partition-3，Consumer从3个Partition接收的消息并不一定是Producer发送的顺序，因此，多个Partition只能保证接收消息大概率按发送时间有序，并不能保证完全按Producer发送的顺序。这一点在使用Kafka作为消息服务器时要特别注意，对发送顺序有严格要求的Topic只能有一个Partition。


Kafka的另一个特点是消息发送和接收都尽量使用批处理，一次处理几十甚至上百条消息，比一次一条效率要高很多。


最后要注意的是消息的持久性。Kafka总是将消息写入Partition对应的文件，消息保存多久取决于服务器的配置，可以按照时间删除（默认3天），也可以按照文件大小删除，因此，只要Consumer在离线期内的消息还没有被删除，再次上线仍然可以接收到完整的消息流。这一功能实际上是客户端自己实现的，客户端会存储它接收到的最后一个消息的offsetId，再次上线后按上次的offsetId查询。offsetId是Kafka标识某个Partion的每一条消息的递增整数，客户端通常将它存储在ZooKeeper中。


有了Kafka消息设计的基本概念，我们来看看如何在Spring Boot中使用Kafka。


### 安装Kafka


首先从Kafka官网下载最新版Kafaka，解压后在bin目录找到两个文件：

`bin`
- zookeeper-server-start.sh：启动ZooKeeper（已内置在Kafka中）；
`zookeeper-server-start.sh`
- kafka-server-start.sh：启动Kafka。
`kafka-server-start.sh`

先启动ZooKeeper：


```
$ ./zookeeper-server-start.sh ../config/zookeeper.properties
```


再启动Kafka：


```
./kafka-server-start.sh ../config/server.properties
```


看到如下输出表示启动成功：


```
... INFO [KafkaServer id=0] started (kafka.server.KafkaServer)
```


如果要关闭Kafka和ZooKeeper，依次按Ctrl-C退出即可。注意这是在本地开发时使用Kafka的方式，线上Kafka服务推荐使用云服务厂商托管模式（AWS的MSK，阿里云的消息队列Kafka版）。


### 使用Kafka


在Spring Boot中使用Kafka，首先要引入依赖：


```
<dependency><groupId>org.springframework.kafka</groupId><artifactId>spring-kafka</artifactId></dependency>
```


注意这个依赖是spring-kafka项目提供的。

`spring-kafka`

然后，在application.yml中添加Kafka配置：

`application.yml`

```
spring:kafka:bootstrap-servers:localhost:9092consumer:auto-offset-reset:latestmax-poll-records:100max-partition-fetch-bytes:1000000
```


除了bootstrap-servers必须指定外，consumer相关的配置项均为调优选项。例如，max-poll-records表示一次最多抓取100条消息。配置名称去哪里看？IDE里定义一个KafkaProperties.Consumer的变量：

`bootstrap-servers`
`consumer`
`max-poll-records`
`KafkaProperties.Consumer`

```
KafkaProperties.Consumerc=null;
```


然后按住Ctrl查看源码即可。


### 发送消息


Spring Boot自动为我们创建一个KafkaTemplate用于发送消息。注意到这是一个泛型类，而默认配置总是使用String作为Kafka消息的类型，所以注入KafkaTemplate<String, String>即可：

`KafkaTemplate`
`String`
`KafkaTemplate<String, String>`

```
@ComponentpublicclassMessagingService{@AutowiredObjectMapper objectMapper;@AutowiredKafkaTemplate<String, String> kafkaTemplate;publicvoidsendRegistrationMessage(RegistrationMessage msg)throwsIOException {
        send("topic_registration", msg);
    }publicvoidsendLoginMessage(LoginMessage msg)throwsIOException {
        send("topic_login", msg);
    }privatevoidsend(String topic, Object msg)throwsIOException {
        ProducerRecord<String, String> pr =newProducerRecord<>(topic, objectMapper.writeValueAsString(msg));
        pr.headers().add("type", msg.getClass().getName().getBytes(StandardCharsets.UTF_8));
        kafkaTemplate.send(pr);
    }
}
```


发送消息时，需指定Topic名称，消息正文。为了发送一个JavaBean，这里我们没有使用MessageConverter来转换JavaBean，而是直接把消息类型作为Header添加到消息中，Header名称为type，值为Class全名。消息正文是序列化的JSON。

`MessageConverter`
`type`

### 接收消息


接收消息可以使用@KafkaListener注解：

`@KafkaListener`

```
@ComponentpublicclassTopicMessageListener{privatefinalLoggerlogger=LoggerFactory.getLogger(getClass());@AutowiredObjectMapper objectMapper;@KafkaListener(topics = "topic_registration", groupId = "group1")publicvoidonRegistrationMessage(@PayloadString message,@Header("type")String type)throwsException {RegistrationMessagemsg=objectMapper.readValue(message, getType(type));
        logger.info("received registration message: {}", msg);
    }@KafkaListener(topics = "topic_login", groupId = "group1")publicvoidonLoginMessage(@PayloadString message,@Header("type")String type)throwsException {LoginMessagemsg=objectMapper.readValue(message, getType(type));
        logger.info("received login message: {}", msg);
    }@KafkaListener(topics = "topic_login", groupId = "group2")publicvoidprocessLoginMessage(@PayloadString message,@Header("type")String type)throwsException {LoginMessagemsg=objectMapper.readValue(message, getType(type));
        logger.info("process login message: {}", msg);
    }@SuppressWarnings("unchecked")privatestatic<T> Class<T>getType(String type){//TODO:use cache:try{return(Class<T>) Class.forName(type);
        }catch(ClassNotFoundException e) {thrownewRuntimeException(e);
        }
    }
}
```


在接收消息的方法中，使用@Payload表示传入的是消息正文，使用@Header可传入消息的指定Header，这里传入@Header("type")，就是我们发送消息时指定的Class全名。接收消息时，我们需要根据Class全名来反序列化获得JavaBean。

`@Payload`
`@Header`
`@Header("type")`

上述代码一共定义了3个Listener，其中有两个方法监听的是同一个Topic，但它们的Group ID不同。假设Producer发送的消息流是A、B、C、D，Group ID不同表示这是两个不同的Consumer，它们将分别收取完整的消息流，即各自均收到A、B、C、D。Group ID相同的多个Consumer实际上被视作一个Consumer，即如果有两个Group ID相同的Consumer，那么它们各自收到的很可能是A、C和B、D。


运行应用程序，注册新用户后，观察日志输出：


```
... c.i.learnjava.service.UserService        : try register by bob@example.com...
... c.i.learnjava.web.UserController         : user registered: bob@example.com
... c.i.l.service.TopicMessageListener       : received registration message: [RegistrationMessage: email=bob@example.com, name=Bob, timestamp=1594637517458]
```


用户登录后，观察日志输出：


```
... c.i.learnjava.service.UserService        : try login by bob@example.com...
... c.i.l.service.TopicMessageListener       : received login message: [LoginMessage: email=bob@example.com, name=Bob, success=true, timestamp=1594637523470]
... c.i.l.service.TopicMessageListener       : process login message: [LoginMessage: email=bob@example.com, name=Bob, success=true, timestamp=1594637523470]
```


因为Group ID不同，同一个消息被两个Consumer分别独立接收。如果把Group ID改为相同，那么同一个消息只会被两者之一接收。


有细心的童鞋可能会问，在Kafka中是如何创建Topic的？又如何指定某个Topic的分区数量？


实际上开发使用的Kafka默认允许自动创建Topic，创建Topic时默认的分区数量是2，可以通过server.properties修改默认分区数量。

`server.properties`

在生产环境中通常会关闭自动创建功能，Topic需要由运维人员先创建好。和RabbitMQ相比，Kafka并不提供网页版管理后台，管理Topic需要使用命令行，比较繁琐，只有云服务商通常会提供更友好的管理后台。


### 练习


在Spring Boot中使用Kafka。


下载练习


### 小结


Spring Boot通过KafkaTemplate发送消息，通过@KafkaListener接收消息；


配置Consumer时，指定Group ID非常重要。

