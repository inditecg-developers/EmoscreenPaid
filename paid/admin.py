from django.contrib import admin

from . import models


admin.site.register(models.EsCfgForm)
admin.site.register(models.EsCfgSection)
admin.site.register(models.EsCfgOptionSet)
admin.site.register(models.EsCfgOption)
admin.site.register(models.EsCfgQuestion)
admin.site.register(models.EsCfgScale)
admin.site.register(models.EsCfgScaleItem)
admin.site.register(models.EsCfgThreshold)
admin.site.register(models.EsCfgDerivedList)
admin.site.register(models.EsCfgEvaluationRule)
admin.site.register(models.EsCfgReportTemplate)
admin.site.register(models.EsCfgReportBlock)
admin.site.register(models.EsCfgReportBlockSection)
admin.site.register(models.EsCfgReportBlockScale)
admin.site.register(models.EsPayOrder)
admin.site.register(models.EsPayTransaction)
admin.site.register(models.EsPayRevenueSplit)
admin.site.register(models.EsPayEmailLog)
admin.site.register(models.EsSubSubmission)
admin.site.register(models.EsSubAnswer)
admin.site.register(models.EsSubScaleScore)
admin.site.register(models.EsRepReport)
