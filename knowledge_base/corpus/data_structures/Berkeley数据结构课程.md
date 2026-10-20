# Berkeley数据结构课程

> 文档ID: f7d9c9ea34401c06930c
> 来源: https://fa26.datastructur.es/
> 来源站点: fa26.datastructur.es
> 来源类型: public-course
> 大学: University of California, Berkeley
> 课程: CS 61B Data Structures
> 作者或机构: UC Berkeley CS 61B instructors
> 授权: source-terms
> 采集范围: public-course-page
> 语言: en
> 爬取时间: 2026-10-09T13:46:11.919541+00:00
> 更新时间: 2026-10-09T13:46:11.919541+00:00
> 内容哈希: 8a3ca3e4836a83a153d896c8919fc97433dfc73f44faf91921f67c9ed349a72b
> 学科: data_structures | 难度: 基础
> 标签: 数据结构, 链表, 树, 哈希表, 图, Java, 大学公开课

---

# CS 61B Fall 2026


Lecture : MWF, 2-3pm, Wheeler 150 [ Live Lecture Recordings , Lecture Code ]


## Announcements


## Week 7

- Deadlines Project 3 (Percolation) : due Tuesday 10/6 at 11:59 PM PT Homework 4 : due Friday 10/9 at 11:59 PM PT Project 4 (Timeseries and NGramMap) : due Tuesday 10/13 at 11:59 PM PT Week 6 Survey : due Tuesday 10/6 at 11:59pm PT with a 24 hour grace period Week 7 Survey : due Tuesday 10/13 at 11:59pm PT with a 24 hour grace period
- Tutoring (SGT) Sign-ups are available on the section tool . Check out Ed for details on sign ups and attendance policies.

See Ed for the full announcements .


Past announcements


## Course Calendar Show Only Finalized Schedule


Skip to current week


| Wk. | Date | Lecture | Sections | Lab | HW | Project |
| --- | --- | --- | --- | --- | --- | --- |
| 1 Survey (due Fri Aug 28) | Wed Aug 26 | 1. Welcome to 61B, Intro to Java ( Ch. 1 ) Slides / Video | No Discussion | Lab 1 | Tools HW1: Setup (due Fri Aug 28) |  |
| Fri Aug 28 | 2. Defining and Using Classes, Lists ( Ch. 2 ) Slides / Video | Coding HW2: Java Intro (due Tue Sep 01) |  |  |  |  |
| 2 Survey (due Tue Sep 08) | Mon Aug 31 | 3. Lists, Arrays, Maps, References ( Ch. 3 ) Slides / Video | 1. Classes, Lists, Maps, Arrays, References Discussion: Worksheet / Solutions | Lab 2: Debugging | Mini Project 0: Particle Simulator (due Tue Sep 08) |  |
| Wed Sep 02 | 4. Packages, Recursion, IntLists ( Ch. 4 ) Slides / Video |  |  |  |  |  |
| Fri Sep 04 | 5. Testing ( Ch. 5 ) Slides / Video Bonus Video | Coding HW3: IntLists (due Tue Sep 08) |  |  |  |  |
| 3 Survey (due Tue Sep 15) | Mon Sep 07 | No Lecture (Labor Day) | 2. No Section Discussion: Worksheet / Solutions | Lab 3: Linked Lists |  |  |
| Wed Sep 09 | 6. SLLists, Nested Classes, Sentinel Nodes ( Ch. 6 ) Slides / Video |  | Mini Project 1: Deques (due Wed Sep 16) 1A: Deques and Tests / 1B: LinkedListDeque 1A due Fri 9/11, 1B due Wed 9/16 |  |  |  |
| Fri Sep 11 | 7. DLLists, Basic ALists ( Ch. 7 ) Slides / Video |  |  |  |  |  |
| 4 Survey (due Tue Sep 22) | Mon Sep 14 | 8. Resizing and Circular Arrays ( Ch. 8 ) Slides / Video | 3. SLLists, DLLists, ALists Discussion: Worksheet / Solutions | Lab 4: Git |  |  |
| Wed Sep 16 | 9. Interface and Implementation Inheritance ( Ch. 9 ) Slides / Video | Mini Project 2: ArrayDeque (due Tue Sep 22) Released Mon 9/14 |  |  |  |  |
| Fri Sep 18 | 10. Iterators, Iterables, and Equals ( Ch. 11 ) Slides / Video |  |  |  |  |  |
| 5 Survey (due Tue Sep 29) | Mon Sep 21 | 11. Subtype Polymorphism, Comparables, Comparators ( Ch. 10 ) Slides / Video | 4. Default Methods, Iterators, Equals Discussion: Worksheet / Solutions | Lab 5: Comparables and Comparators |  |  |
| Wed Sep 23 | 12. Review, Midterm Practice Slides Mini-Midterm 1: Wed Sep 23, 8-9:20 PM |  |  |  |  |  |
| Fri Sep 25 | 13. Asymptotics I ( Ch. 12 ) Slides / Video |  |  |  |  |  |
| 6 Survey (due Tue Oct 06) | Mon Sep 28 | 14. Disjoint Sets ( Ch. 15 ) Slides / Video | 5. Comparison, Intro to Asymptotics Discussion: Worksheet / Solutions | Lab 6: Disjoint Sets | Mini Project 3: Percolation (due Tue Oct 06) |  |
| Wed Sep 30 | 15. Asymptotics II ( Ch. 13 ) Slides / Video |  |  |  |  |  |
| Fri Oct 02 | 16. Asymptotics III ( Ch. 14 ) Slides / Video |  |  |  |  |  |
| 7 Survey (due Tue Oct 13) | Mon Oct 05 | 17. Sets, Extends, and BSTs ( Ch. 16 ) Slides / Video | 6. Asymptotics II Discussion: Worksheet / Solutions | Lab 7: Timing Experiments |  |  |
| Wed Oct 07 | 18. B-Trees ( Ch. 17 ) Slides / Video | Theory HW4: Asymptotic Analysis (due Fri Oct 09) | Design Project 4A: TimeSeries and NGramMap (due Tue Oct 13) |  |  |  |
| Fri Oct 09 | 19. Red-Black Trees ( Ch. 18 ) Slides |  |  |  |  |  |
| 8 Survey (due Tue Oct 20) | Mon Oct 12 | 20. Heaps, Priority Queues, and Tree Representations ( Ch. 19 ) Slides | 7. BSTs, B-Trees, and LLRBs | Lab 8: BSTs and LLRBs |  |  |
| Wed Oct 14 | 21. Tree and Graph Traversals ( Ch. 20 ) Slides | Design Project 4B: Wordnet (Design) (due Tue Oct 20) |  |  |  |  |
| Fri Oct 16 | 22. Graph Traversals and Implementations ( Ch. 21 ) Slides | Coding HW5: BSTMaps (due Fri Oct 16) |  |  |  |  |
| 9 Survey (due Tue Oct 27) | Mon Oct 19 | 23. Shortest Paths ( Ch. 22 ) Slides | 8. Tree Traversals, Graphs | Lab 9: Graphs |  |  |
| Wed Oct 21 | 24. Minimum Spanning Trees ( Ch. 23 ) Slides | Design Project 4C: Wordnet (k == 0) (due Fri Oct 30) |  |  |  |  |
| Fri Oct 23 | 25. Directed Acyclic Graphs ( Ch. 24 ) Slides |  |  |  |  |  |
| 10 Survey (due Tue Nov 03) | Mon Oct 26 | 26. Hashing I ( Ch. 25 ) Slides | 9. Shortest Paths, MSTs | Lab 10: Shortest Paths |  |  |
| Wed Oct 28 | 27. Hashing II ( Ch. 26 ) Slides |  |  |  |  |  |
| Fri Oct 30 | 28. Tries ( Ch. 27 ) Slides |  |  |  |  |  |
| 11 | Mon Nov 02 | 29. Software Engineering I ( Ch. 28 ) | 10. Midterm 2 Review | Lab 11: Hashing | Theory HW6: Midterm Review (due Tue Nov 03) |  |
| Wed Nov 04 | 30. Midterm Review Midterm 2: Wed Nov 4, 8-10 PM |  | Design Project 4D: Wordnet (k != 0) (due Fri Nov 13) |  |  |  |
| Fri Nov 06 | 31. Software Engineering II - BYOW Warmup Slides |  |  |  |  |  |
| 12 Survey (due Tue Nov 17) | Mon Nov 09 | 32. Basic Sorts ( Ch. 30 ) Slides | 11. Hashing, Tries | Lab 12: BYOW Intro | Coding HW7: HashMaps (due Tue Nov 10) |  |
| Wed Nov 11 | No Lecture (Veterans Day) |  |  |  |  |  |
| Fri Nov 13 | 33. Insertion Sort and Intro to Quicksort ( Ch. 30 ) Slides |  |  |  |  |  |
| 13 Survey (due Tue Nov 24) | Mon Nov 16 | 34. Quicksort ( Ch. 31 ) Slides | 12. Sorting | Lab 13: Sorts | Design Project 5A: BYOW Design (due Wed Nov 18) |  |
| Wed Nov 18 | 35. Sorting and Algorithmic Bounds ( Ch. 33 ) Slides |  |  |  |  |  |
| Fri Nov 20 | 36. Radix Sorts ( Ch. 34 ) Slides | Design Project 5B: BYOW World Generation (due Tue Nov 24) |  |  |  |  |
| 14 | Mon Nov 23 | 37. The Social Implications of Computing Slides | No Discussion (Thanksgiving Break) | Lab 14: No lab |  |  |
| Wed Nov 25 | No Lecture (Thanksgiving Break) | Design Project 5C: BYOW Interactivity (due Tue Dec 01) |  |  |  |  |
| Fri Nov 27 |  |  |  |  |  |  |
| 15 Survey (due Tue Dec 08) | Mon Nov 30 | 38. Software Engineering III - AI in Software Engineering ( Ch. 36 ) Slides | 13. Sorting II | Lab 15: Agentic Development |  |  |
| Wed Dec 02 | 39. Compression ( Ch. 38 ) Slides |  |  |  |  |  |
| Fri Dec 04 | 40. Summary, Fun Slides |  |  |  |  |  |
| 16 | Mon Dec 07 | No Lecture (RRR Week) | No Discussion (RRR Week) |  |  |  |
| Wed Dec 09 |  |  |  |  |  |  |
| Fri Dec 11 | Theory HW8: Final Review (due Fri Dec 11) |  |  |  |  |  |
| 17 | Fri Dec 18 | Final Exam: Thu Dec 17, 3-6 PM |  |  |  |  |
