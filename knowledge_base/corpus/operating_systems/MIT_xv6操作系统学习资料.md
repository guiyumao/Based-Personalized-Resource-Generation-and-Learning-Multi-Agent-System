# MIT_xv6操作系统学习资料

> 文档ID: 1337867b2baffddb1f1c
> 来源: https://ocw.mit.edu/courses/6-828-operating-system-engineering-fall-2012/pages/study-materials/
> 来源站点: ocw.mit.edu
> 来源类型: open-courseware
> 大学: Massachusetts Institute of Technology
> 课程: 6.828 Operating System Engineering
> 作者或机构: Frans Kaashoek; Robert Morris
> 授权: CC BY-NC-SA
> 采集范围: public-course-page
> 语言: en
> 爬取时间: 2026-10-09T13:45:38.085080+00:00
> 更新时间: 2026-10-09T13:45:38.085080+00:00
> 内容哈希: fea03bd66aff948e9e8878bc0b4dbb0fab8aedee64c6f249ce89d7a75f705843
> 学科: operating_systems | 难度: 进阶
> 标签: 操作系统, xv6, Unix, 并发, 文件系统, 内核

---

### Introduction


Xv6 is a teaching operating system developed in the summer of 2006 for MIT’s operating systems course, 6.828: Operating System Engineering. We hope that xv6 will be useful in other courses too. This page collects resources to aid the use of xv6 in other courses, including a commentary on the source code itself.


### History and Background


For many years, MIT had no operating systems course. In the fall of 2002, one was created to teach operating systems engineering. In the course lectures, the class worked through Sixth Edition Unix (aka V6) using John Lions’s famous commentary. In the lab assignments, students wrote most of an exokernel operating system, eventually named Jos, for the Intel x86. Exposing students to multiple systems–V6 and Jos–helped develop a sense of the spectrum of operating system designs.


V6 presented pedagogic challenges from the start. Students doubted the relevance of an obsolete 30-year-old operating system written in an obsolete programming language (pre-K&R C) running on obsolete hardware (the PDP-11). Students also struggled to learn the low-level details of two different architectures (the PDP-11 and the Intel x86) at the same time. By the summer of 2006, we had decided to replace V6 with a new operating system, xv6, modeled on V6 but written in ANSI C and running on multiprocessor Intel x86 machines. Xv6’s use of the x86 makes it more relevant to students’ experience than V6 was and unifies the course around a single architecture. Adding multiprocessor support requires handling concurrency head on with locks and threads (instead of using special-case solutions for uniprocessors such as enabling / disabling interrupts) and helps relevance. Finally, writing a new system allowed us to write cleaner versions of the rougher parts of V6, like the scheduler and file system. 6.828 substituted xv6 for V6 in the fall of 2006.


### Xv6 Sources and Text


The latest xv6 source is available via


git clone git://pdos.csail.mit.edu/xv6/xv6.git


We also distribute the sources as a printed booklet with line numbers that keep everyone together during lectures. The booklet is available in the lecture notes section. To get the version corresponding to this booklet, run


git checkout -b xv6-rev7 xv6-rev7


The xv6 source code is licensed under the traditional MIT license ; see the LICENSE file in the source distribution. To help students read through xv6 and learn about the main ideas in operating systems we also distribute a textbook / commentary for the latest xv6, available in the lecture notes section. The line numbers in this book refer to the above source booklet.


xv6 compiles using the GNU C compiler, targeted at the x86 using ELF binaries. On BSD and Linux systems, you can use the native compilers; On OS X, which doesn’t use ELF binaries, you must use a cross-compiler. Xv6 does boot on real hardware, but typically we run it using the QEMU emulator. Both the GCC cross compiler and QEMU can be found on the 6.828 tools page.


### Xv6 Lecture Material


In 6.828, the lectures in the first half of the course cover the xv6 sources and text. The lectures in the second half consider advanced topics using research papers; for some, xv6 serves as a useful base for making discussions concrete.


### Unix Version 6


6.828’s xv6 is inspired by Unix V6 and by:

- Lions, John. Lions’ Commentary on UNIX . 6th ed. Peer to Peer Communications, 1977. ISBN: 9781573980135. An on-line version of the Lions commentary , and the source code . The v6 source code is also available online through the PDP Unix Preservation Society .

The following are useful to read the original code:

- Digital Equipment. The PDP11 / 40 Processor Handbook . Digital Equipment Corporation, 1972.
