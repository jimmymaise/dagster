import inspect
from typing import Any, Optional, Type

from pydantic import BaseModel
from pydantic.fields import SHAPE_SINGLETON, ModelField

import dagster._check as check
from dagster import Field, Shape
from dagster._config.field_utils import (
    FIELD_NO_DEFAULT_PROVIDED,
    config_dictionary_from_values,
    convert_potential_field,
)
from dagster._core.definitions.resource_definition import ResourceDefinition


class Config(BaseModel):
    """
    Base class for Dagster configuration models.
    """


class StructuredConfigResource(
    ResourceDefinition,
    Config,
):
    def __init__(self, **data: Any):
        schema = infer_schema_from_config_class(self.__class__)

        inner_resource_def = ResourceDefinition(self.resource_fn, schema)
        configured_resource_def = inner_resource_def.configured(
            config_dictionary_from_values(
                data,
                schema,
            ),
        )

        Config.__init__(self, **data)
        ResourceDefinition.__init__(
            self,
            resource_fn=self.resource_fn,
            config_schema=configured_resource_def.config_schema,
            description=self.__doc__,
        )

    def __setattr__(self, name: str, value: Any):
        # This is a hack to allow us to set attributes on the class that are not part of the
        # config schema. Pydantic will normally raise an error if you try to set an attribute
        # that is not part of the schema.

        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return

        return super().__setattr__(name, value)

    def resource_fn(self, context) -> Any:  # pylint: disable=unused-argument
        pass


def _convert_pydantic_field(pydantic_field: ModelField) -> Field:
    """
    Transforms a Pydantic field into a corresponding Dagster config field.
    """

    if _safe_is_subclass(pydantic_field.type_, Config):
        return infer_schema_from_config_class(
            pydantic_field.type_, description=pydantic_field.field_info.description
        )

    dagster_type = pydantic_field.type_
    if pydantic_field.shape != SHAPE_SINGLETON:
        raise NotImplementedError(f"Pydantic shape {pydantic_field.shape} not supported")

    inner_config_type = convert_potential_field(dagster_type).config_type
    return Field(
        config=inner_config_type,
        description=pydantic_field.field_info.description,
        default_value=pydantic_field.default
        if pydantic_field.default
        else FIELD_NO_DEFAULT_PROVIDED,
    )


def infer_schema_from_config_annotation(model_cls: Any, config_arg_default: Any) -> Field:
    """
    Parses a structured config class or primitive type and returns a corresponding Dagster config Field.
    """

    if _safe_is_subclass(model_cls, Config):
        check.invariant(
            config_arg_default is inspect.Parameter.empty,
            "Cannot provide a default value when using a Config class",
        )
        return infer_schema_from_config_class(model_cls)

    inner_config_type = convert_potential_field(model_cls).config_type
    return Field(
        config=inner_config_type,
        default_value=FIELD_NO_DEFAULT_PROVIDED
        if config_arg_default is inspect.Parameter.empty
        else config_arg_default,
    )


def _safe_is_subclass(cls: Any, possible_parent_cls: Type) -> bool:
    """Version of issubclass that returns False if cls is not a Type."""
    if not isinstance(cls, type):
        return False
    return issubclass(cls, possible_parent_cls)


def infer_schema_from_config_class(
    model_cls: Type[Config], description: Optional[str] = None
) -> Field:
    """
    Parses a structured config class and returns a corresponding Dagster config Field.
    """

    check.param_invariant(
        issubclass(model_cls, Config),
        "Config type annotation must inherit from dagster._config.structured_config.Config",
    )

    fields = {}
    for pydantic_field_name, pydantic_field in model_cls.__fields__.items():
        fields[pydantic_field_name] = _convert_pydantic_field(pydantic_field)

    docstring = model_cls.__doc__.strip() if model_cls.__doc__ else None
    return Field(config=Shape(fields), description=description or docstring)
