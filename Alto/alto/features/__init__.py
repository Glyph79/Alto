# alto/features/__init__.py
from typing import List, Type
from .base import OptionalFeature
from .custom_fallbacks import CustomFallbacksFeature

def get_optional_features() -> List[Type[OptionalFeature]]:
    return [CustomFallbacksFeature]