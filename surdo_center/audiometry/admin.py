from django.contrib import admin

from .models import (
    AudiometryCalculation,
    AudiometryExam,
    AudiometryMeasurement,
    DecisionAnalysis,
    DecisionRule,
    DecisionRuleHit,
    DecisionRuleSet,
)


admin.site.register(AudiometryExam)
admin.site.register(AudiometryMeasurement)
admin.site.register(AudiometryCalculation)
admin.site.register(DecisionRuleSet)
admin.site.register(DecisionRule)
admin.site.register(DecisionAnalysis)
admin.site.register(DecisionRuleHit)
