-- ============================================================
-- AgentCore 测试数据
-- ============================================================

-- 用户画像（3个不同方向的典型用户）
INSERT INTO user_profile (user_id, knowledge_base, cognitive_style, error_preference, learning_speed, interest_direction, goal_orientation)
VALUES
(1001, 'Java基础, Python入门, 数据结构', '动手实践型', '并发编程, 数据库优化, JVM调优', '适中', '后端开发, 微服务架构', '找到Java后端实习岗位'),
(1002, 'C语言基础, 计算机组成原理', '视觉型', '指针操作, 内存管理, 链表', '较慢', '嵌入式开发, 操作系统', '考研计算机专业'),
(1003, 'JavaScript, HTML, CSS, Vue3', '文本型', '异步编程, 状态管理, 性能优化', '较快', '前端开发, React, TypeScript', '转行前端工程师');

-- 生成资源（覆盖5种类型）
INSERT INTO resource (user_id, resource_type, title, content, format, knowledge_point, difficulty_level, estimated_time_minutes, status)
VALUES
(1001, 'lecture', 'Java线程池原理与实践', '# Java线程池原理与实践\n\n## 概述\n线程池是多线程编程中的核心概念...\n\n## 核心参数\n1. corePoolSize：核心线程数\n2. maximumPoolSize：最大线程数\n3. keepAliveTime：空闲线程存活时间\n4. workQueue：工作队列\n\n## 实践建议\n...', 'markdown', 'Java线程池', 'medium', 20, 'ready'),
(1001, 'mindmap', 'Java并发编程知识体系', '# 并发编程\n## 线程基础\n### 线程创建方式\n### 线程生命周期\n## 锁机制\n### synchronized\n### ReentrantLock\n### 读写锁\n## 并发工具\n### CountDownLatch\n### CyclicBarrier\n### Semaphore\n## 线程池\n### 核心参数\n### 拒绝策略', 'markdown', '并发编程', 'medium', 10, 'ready'),
(1001, 'exercise', '线程池参数配置练习', '## 选择题\n\n### 题目1\n以下关于线程池核心参数的说法，哪个是正确的？\n\nA. corePoolSize必须大于maximumPoolSize\nB. keepAliveTime对所有线程都生效\nC. workQueue满了才会创建新线程直到maximumPoolSize\nD. 线程池默认使用AbortPolicy拒绝策略\n\n**正确答案：C**\n\n**解析：当工作队列满且当前线程数小于maximumPoolSize时，线程池会创建新线程来处理任务。**\n\n### 题目2\n如果需要一个无界线程池，应该使用哪个工厂方法？\n\nA. newFixedThreadPool\nB. newCachedThreadPool\nC. newSingleThreadExecutor\nD. newScheduledThreadPool\n\n**正确答案：B**\n\n**解析：newCachedThreadPool创建的线程池corePoolSize为0，maximumPoolSize为Integer.MAX_VALUE。**', 'markdown', 'Java线程池', 'medium', 30, 'ready'),
(1001, 'code_example', '自定义线程池实战', '## 场景：Web服务器请求处理\n\n```java\nimport java.util.concurrent.*;\n\npublic class CustomThreadPool {\n    public static void main(String[] args) {\n        // 自定义线程池参数\n        ThreadPoolExecutor executor = new ThreadPoolExecutor(\n            4,                          // corePoolSize\n            8,                          // maximumPoolSize\n            60L, TimeUnit.SECONDS,      // keepAliveTime\n            new LinkedBlockingQueue<>(100), // workQueue\n            new ThreadPoolExecutor.CallerRunsPolicy() // 拒绝策略\n        );\n        \n        // 提交任务\n        for (int i = 0; i < 10; i++) {\n            final int taskId = i;\n            executor.submit(() -> {\n                System.out.println("任务" + taskId + " 由线程" + \n                    Thread.currentThread().getName() + "执行");\n                try {\n                    Thread.sleep(1000);\n                } catch (InterruptedException e) {\n                    Thread.currentThread().interrupt();\n                }\n            });\n        }\n        \n        executor.shutdown();\n    }\n}\n```\n\n## 关键代码解析\n- `LinkedBlockingQueue<>(100)`：容量100的有界队列\n- `CallerRunsPolicy()`：队列满时由调用线程执行，提供背压机制', 'markdown', 'Java线程池', 'medium', 25, 'ready'),
(1001, 'extended_reading', '深入理解Java并发编程', '## 推荐阅读\n\n### 入门级\n1. **《Java并发编程实战》** - Brian Goetz\n   - 并发编程圣经，适合系统学习\n\n### 进阶级\n2. **《Java并发编程的艺术》** - 方腾飞\n   - 深入讲解JUC包原理\n\n3. **并发编程网** - http://ifeve.com\n   - 大量并发编程实战案例\n\n### 在线资源\n4. **Oracle官方并发教程**\n5. **极客时间《Java并发编程实战》专栏**', 'markdown', '并发编程', 'hard', 15, 'ready'),
(1002, 'lecture', 'C语言指针深入讲解', '# C语言指针深入讲解\n\n## 指针基础\n指针是C语言的灵魂...\n\n## 指针与数组\n```c\nint arr[5] = {1, 2, 3, 4, 5};\nint *p = arr;  // p指向arr的首元素\n```\n\n## 常见误区\n1. 野指针：未初始化的指针\n2. 悬空指针：指向已释放内存\n3. 内存泄漏：未释放动态分配的内存', 'markdown', 'C指针', 'hard', 20, 'ready'),
(1003, 'lecture', 'React Hooks入门指南', '# React Hooks入门指南\n\n## useState\n```jsx\nconst [count, setCount] = useState(0);\n```\n\n## useEffect\n```jsx\nuseEffect(() => {\n  fetchData();\n}, []);\n```\n\n## 自定义Hook\n将组件逻辑提取为可复用的函数', 'markdown', 'React Hooks', 'easy', 20, 'ready'),
(1003, 'code_example', 'React Hooks实战案例', '## TODO应用\n\n```jsx\nimport React, { useState, useEffect } from ''react'';\n\nfunction TodoApp() {\n  const [todos, setTodos] = useState([]);\n  const [input, setInput] = useState('''');\n  \n  const addTodo = () => {\n    if (input.trim()) {\n      setTodos([...todos, { id: Date.now(), text: input, done: false }]);\n      setInput('''');\n    }\n  };\n  \n  return (\n    <div>\n      <input value={input} onChange={e => setInput(e.target.value)} />\n      <button onClick={addTodo}>添加</button>\n      <ul>\n        {todos.map(todo => (\n          <li key={todo.id}>{todo.text}</li>\n        ))}\n      </ul>\n    </div>\n  );\n}\n```', 'markdown', 'React Hooks', 'easy', 25, 'ready');

-- 学习路径
INSERT INTO learning_path (user_id, title, description, subject, status, total_nodes, completed_nodes)
VALUES
(1001, 'Java后端开发学习路径', '从Java基础到Spring Boot微服务全面掌握', '后端开发', 'active', 5, 1);

INSERT INTO learning_path_node (learning_path_id, parent_node_id, knowledge_id, title, description, resource_type_hint, sort_order, estimated_time_minutes, status, resource_ids)
VALUES
(1, NULL, 'java-basics', 'Java基础巩固', '复习Java核心语法与面向对象编程', 'lecture', 1, 120, 'completed', '1'),
(1, 1, 'concurrency', 'Java并发编程', '深入学习多线程与并发工具', 'lecture', 2, 180, 'in_progress', '2,3,4,5'),
(1, 2, 'spring-boot', 'Spring Boot框架', '学习Spring Boot核心特性与开发', 'code_example', 3, 240, 'pending', NULL),
(1, 3, 'microservices', '微服务架构', '学习微服务设计模式与实践', 'lecture', 4, 300, 'pending', NULL),
(1, 4, 'project', '综合项目实战', '完成一个完整的后端项目', 'code_example', 5, 480, 'pending', NULL);

-- 知识库（供RAG检索，embedding需运行时调用API生成）
INSERT INTO knowledge_base (title, content, content_type, knowledge_point, source)
VALUES
('Java线程池核心原理', '线程池是一种多线程处理形式，处理过程中将任务添加到队列，然后在创建线程后自动启动这些任务。线程池的核心参数包括：corePoolSize（核心线程数）、maximumPoolSize（最大线程数）、keepAliveTime（空闲线程存活时间）、workQueue（工作队列）、threadFactory（线程工厂）、handler（拒绝策略）。常见的拒绝策略有：AbortPolicy（抛出异常）、CallerRunsPolicy（由调用线程执行）、DiscardPolicy（丢弃任务）、DiscardOldestPolicy（丢弃最老任务）。', 'text', 'Java线程池', 'Java官方文档'),
('Spring Boot自动配置原理', 'Spring Boot的自动配置通过@EnableAutoConfiguration注解实现，该注解通过@Import导入AutoConfigurationImportSelector类。在Spring Boot启动时，会从META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports文件中读取所有自动配置类。每个自动配置类都使用@Configuration和@ConditionalOnClass、@ConditionalOnMissingBean等条件注解来控制是否生效。开发者可以通过exclude属性排除不需要的自动配置，也可以自定义自动配置类来覆盖默认行为。', 'text', 'Spring Boot', 'Spring官方文档'),
('React虚拟DOM与Diff算法', 'React使用虚拟DOM（Virtual DOM）来提高渲染性能。虚拟DOM是真实DOM的JavaScript对象表示，当状态变化时，React会创建一个新的虚拟DOM树，然后通过Diff算法比较新旧虚拟DOM树的差异，最后只更新需要变化的部分到真实DOM。Diff算法的三个策略：1. 只比较同层节点，不跨层比较；2. 不同类型的元素会产生不同的树；3. 通过key属性来标识列表中的元素，提高列表更新的效率。', 'text', 'React', 'React官方文档'),
('计算机操作系统内存管理', '操作系统内存管理主要包括：内存分配与回收、地址转换、内存保护、虚拟内存。常见的分配算法有：首次适应（First Fit）、最佳适应（Best Fit）、最差适应（Worst Fit）。虚拟内存技术通过页面置换算法（如LRU、FIFO、Clock）来实现，允许进程使用比物理内存更大的地址空间。分页和分段是两种主要的内存管理方式，现代操作系统通常采用段页式结合的方式。', 'text', '操作系统', '计算机操作系统教材');
