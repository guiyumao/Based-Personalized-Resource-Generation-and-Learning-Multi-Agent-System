# 内容与fallback

真实课件3619字符、3道题及QA样本留存，人工评审字段在human-review-samples.json，未做专家准确性验收。真实exercise结果未出现deterministic_fallback；本地结构化/持久化/审核/资源/知识/成绩测试52 passed。

生产练习失败仍可能返回规则fallback且audit_status=passed，该业务语义未改，D-06继续OPEN。通过Schema不等于知识正确；audit unavailable不计审核通过；usage估算不计真实供应商账单。INC-01样本未转为正式live通过。