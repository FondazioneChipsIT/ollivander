from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

__NAMESPACE__ = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"


class AbstractorModeType(Enum):
    """
    Mode for this abstractor.
    """

    MASTER = "master"
    SLAVE = "slave"
    DIRECT = "direct"
    SYSTEM = "system"


class AccessType(Enum):
    """
    The read/write accessability of an addess block.
    """

    READ_ONLY = "read-only"
    WRITE_ONLY = "write-only"
    READ_WRITE = "read-write"
    WRITE_ONCE = "writeOnce"
    READ_WRITE_ONCE = "read-writeOnce"


class ApiType(Enum):
    TGI_2009 = "TGI_2009"
    TGI_2014_BASE = "TGI_2014_BASE"
    TGI_2014_EXTENDED = "TGI_2014_EXTENDED"
    NONE = "none"


class BankAlignmentType(Enum):
    """
    'serial' or 'parallel' bank alignment.
    """

    SERIAL = "serial"
    PARALLEL = "parallel"


class CellClassValueType(Enum):
    """
    Indicates legal cell class values.
    """

    COMBINATIONAL = "combinational"
    SEQUENTIAL = "sequential"


class CellFunctionValueType(Enum):
    """
    Indicates legal cell function values.
    """

    NAND2 = "nand2"
    BUF = "buf"
    INV = "inv"
    MUX21 = "mux21"
    DFF = "dff"
    LATCH = "latch"
    XOR2 = "xor2"
    OTHER = "other"


class CellStrengthValueType(Enum):
    """
    Indicates legal cell strength values.
    """

    LOW = "low"
    MEDIAN = "median"
    HIGH = "high"


@dataclass(kw_only=True)
class ComplexBaseExpression:
    """
    Represents the base-type for an expressions.
    """

    class Meta:
        name = "complexBaseExpression"

    value: str = field(
        default="",
        metadata={
            "min_length": 1,
            "white_space": "collapse",
        },
    )
    other_attributes: dict[str, str] = field(
        default_factory=dict,
        metadata={
            "type": "Attributes",
            "namespace": "##other",
        },
    )


class ComponentPortDirectionType(Enum):
    """
    The direction of a component port.
    """

    IN = "in"
    OUT = "out"
    INOUT = "inout"
    PHANTOM = "phantom"


class DataTypeType(Enum):
    """
    Enumerates C argument data types.
    """

    INT = "int"
    UNSIGNED_INT = "unsigned int"
    LONG = "long"
    UNSIGNED_LONG = "unsigned long"
    FLOAT = "float"
    DOUBLE = "double"
    CHAR = "char *"
    VOID = "void *"


class DelayValueType(Enum):
    """
    Indicates the type of delay value - minimum or maximum delay.
    """

    MIN = "min"
    MAX = "max"


class DelayValueUnitType(Enum):
    """
    Indicates legal units for delay values.
    """

    PS = "ps"
    NS = "ns"


@dataclass(kw_only=True)
class Description:
    """
    Full description string, typically for documentation.
    """

    class Meta:
        name = "description"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    value: str = field(default="")


class Direction(Enum):
    IN = "in"
    OUT = "out"
    INOUT = "inout"


@dataclass(kw_only=True)
class DisplayName:
    """
    Element name for display purposes.

    Typically a few words providing a more detailed and/or user-friendly
    name than the ipxact:name.
    """

    class Meta:
        name = "displayName"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    value: str = field(default="")


class EdgeValueType(Enum):
    """
    Indicates legal values for edge specification attributes.
    """

    RISE = "rise"
    FALL = "fall"


class EndianessType(Enum):
    """
    'big': means the most significant element of any multi-element data
    field is stored at the lowest memory address. 'little' means the least
    significant element of any multi-element data field is stored at the
    lowest memory address.

    If this element is not present the default is 'little' endian.
    """

    BIG = "big"
    LITTLE = "little"


class EnumeratedValueUsage(Enum):
    READ = "read"
    WRITE = "write"
    READ_WRITE = "read-write"


class FormatType(Enum):
    """
    This is an indication on the format of the value. bit: 1-bit or more
    (vector) bits unsigned integer, byte: 8-bit signed integer, shortint:
    16-bit signed integer, int: 32-bit signed integer, longint: 64-bit
    signed integer, shortreal: 32-bit signed floating point number, real:
    64-bit signed floating point number, string: textual information.
    """

    BIT = "bit"
    BYTE = "byte"
    SHORTINT = "shortint"
    INT = "int"
    LONGINT = "longint"
    SHORTREAL = "shortreal"
    REAL = "real"
    STRING = "string"


@dataclass(kw_only=True)
class GeneratorRef:
    """
    A reference to a generator element.
    """

    class Meta:
        name = "generatorRef"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    value: str = field(default="")
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )


@dataclass(kw_only=True)
class Group:
    """
    Indicates which system interface is being mirrored.

    Name must match a group name present on one or more ports in the
    corresonding bus definition.
    """

    class Meta:
        name = "group"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    value: str = field(default="")


class GroupSelectorMultipleGroupSelectionOperator(Enum):
    AND = "and"
    OR = "or"


@dataclass(kw_only=True)
class IndirectAddressRef:
    """
    A reference to a field used for addressing the indirectly accessible
    memoryMap.
    """

    class Meta:
        name = "indirectAddressRef"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    value: str = field(default="")


@dataclass(kw_only=True)
class IndirectDataRef:
    """
    A reference to a field used for read/write access to the indirectly
    accessible memoryMap.
    """

    class Meta:
        name = "indirectDataRef"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    value: str = field(default="")


class InitiativeType(Enum):
    REQUIRES = "requires"
    PROVIDES = "provides"
    BOTH = "both"
    PHANTOM = "phantom"


class InstanceGeneratorTypeScope(Enum):
    INSTANCE = "instance"
    ENTITY = "entity"


@dataclass(kw_only=True)
class InstanceName:
    """
    An instance name assigned to subcomponent instances and contained
    channels, that is unique within the parent component.
    """

    class Meta:
        name = "instanceName"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    value: str = field(default="")


@dataclass(kw_only=True)
class InterfaceType:
    """
    A representation of a component/bus interface relation; i.e. a bus
    interface belonging to a certain component.

    :ivar component_ref: Reference to a component instance name.
    :ivar bus_ref: Reference to the components  bus interface
    :ivar id:
    """

    class Meta:
        name = "interfaceType"

    component_ref: str = field(
        metadata={
            "name": "componentRef",
            "type": "Attribute",
        }
    )
    bus_ref: str = field(
        metadata={
            "name": "busRef",
            "type": "Attribute",
        }
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )


@dataclass(kw_only=True)
class IpxactUri:
    """
    IP-XACT URI, like a standard xs:anyURI except that it can contain
    environment variables in the ${ } form, to be replaced by their value
    to provide the underlying URI.
    """

    class Meta:
        name = "ipxactURI"

    value: str = field(default="")


class KindType(Enum):
    TLM_PORT = "tlm_port"
    TLM_SOCKET = "tlm_socket"
    SIMPLE_SOCKET = "simple_socket"
    MULTI_SOCKET = "multi_socket"
    CUSTOM = "custom"


@dataclass(kw_only=True)
class LanguageType:
    """
    :ivar value:
    :ivar strict: A value of 'true' indicates that this value must match
        the language being generated for the design.
    """

    class Meta:
        name = "languageType"

    value: str = field(default="")
    strict: bool = field(
        default=False,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class LibraryRefType:
    """
    Base IP-XACT document reference type.

    Contains vendor, library, name and version attributes.
    """

    class Meta:
        name = "libraryRefType"

    vendor: str = field(
        metadata={
            "type": "Attribute",
        }
    )
    library: str = field(
        metadata={
            "type": "Attribute",
        }
    )
    name: str = field(
        metadata={
            "type": "Attribute",
        }
    )
    version: str = field(
        metadata={
            "type": "Attribute",
        }
    )


@dataclass(kw_only=True)
class MemoryMapRefType:
    """
    Base type for an element which references an memory map.

    Reference is kept in an attribute rather than the text value, so that
    the type may be extended with child elements if necessary.

    :ivar memory_map_ref: A reference to a unique memory map.
    """

    class Meta:
        name = "memoryMapRefType"

    memory_map_ref: str = field(
        metadata={
            "name": "memoryMapRef",
            "type": "Attribute",
        }
    )


class ModifiedWriteValueType(Enum):
    ONE_TO_CLEAR = "oneToClear"
    ONE_TO_SET = "oneToSet"
    ONE_TO_TOGGLE = "oneToToggle"
    ZERO_TO_CLEAR = "zeroToClear"
    ZERO_TO_SET = "zeroToSet"
    ZERO_TO_TOGGLE = "zeroToToggle"
    CLEAR = "clear"
    SET = "set"
    MODIFY = "modify"


class ModuleParameterTypeUsageType(Enum):
    NONTYPED = "nontyped"
    TYPED = "typed"


class MonitorInterfaceMode(Enum):
    MASTER = "master"
    SLAVE = "slave"
    SYSTEM = "system"
    MIRRORED_MASTER = "mirroredMaster"
    MIRRORED_SLAVE = "mirroredSlave"
    MIRRORED_SYSTEM = "mirroredSystem"


class OnMasterInitiative(Enum):
    REQUIRES = "requires"
    PROVIDES = "provides"
    BOTH = "both"


class OnSlaveInitiative(Enum):
    REQUIRES = "requires"
    PROVIDES = "provides"
    BOTH = "both"


class OnSystemInitiative(Enum):
    REQUIRES = "requires"
    PROVIDES = "provides"
    BOTH = "both"


class ParameterBaseTypePrefix(Enum):
    DECA = "deca"
    HECTO = "hecto"
    KILO = "kilo"
    MEGA = "mega"
    GIGA = "giga"
    TERA = "tera"
    PETA = "peta"
    EXA = "exa"
    ZETTA = "zetta"
    YOTTA = "yotta"
    DECI = "deci"
    CENTI = "centi"
    MILLI = "milli"
    MICRO = "micro"
    NANO = "nano"
    PICO = "pico"
    FEMTO = "femto"
    ATTO = "atto"
    ZEPTO = "zepto"
    YOCTO = "yocto"


class ParameterBaseTypeUnit(Enum):
    SECOND = "second"
    AMPERE = "ampere"
    KELVIN = "kelvin"
    HERTZ = "hertz"
    JOULE = "joule"
    WATT = "watt"
    COULOMB = "coulomb"
    VOLT = "volt"
    FARAD = "farad"
    OHM = "ohm"
    SIEMENS = "siemens"
    HENRY = "henry"
    CELSIUS = "Celsius"


class ParameterTypeResolve(Enum):
    """
    Determines how a parameter is resolved.

    User means the value must be obtained from the user. Generated means
    the value will be provided by a generator.

    :cvar IMMEDIATE: Property content cannot be modified through
        configuration.
    :cvar USER: Property content can be modified through configuration.
        Modifications will be saved with the design.
    :cvar GENERATED: Generators may modify this property. Modifications
        get saved with the design.
    """

    IMMEDIATE = "immediate"
    USER = "user"
    GENERATED = "generated"


class PayloadType(Enum):
    GENERIC = "generic"
    SPECIFIC = "specific"


class PresenceType(Enum):
    REQUIRED = "required"
    ILLEGAL = "illegal"
    OPTIONAL = "optional"


class ProtocolTypeType(Enum):
    TLM = "tlm"
    CUSTOM = "custom"


class ReadActionType(Enum):
    CLEAR = "clear"
    SET = "set"
    MODIFY = "modify"


class RequiresDriverDriverType(Enum):
    CLOCK = "clock"
    SINGLE_SHOT = "singleShot"
    ANY = "any"


class ReturnTypeType(Enum):
    VOID = "void"
    INT = "int"


class SharedType(Enum):
    """
    The sharedness of the memoryMap content.
    """

    YES = "yes"
    NO = "no"
    UNDEFINED = "undefined"


class SignType(Enum):
    """
    This is an indication of the signedness of the value.
    """

    SIGNED = "signed"
    UNSIGNED = "unsigned"


class SimpleBitSteeringExpressionValue(Enum):
    ON = "on"
    OFF = "off"


class SimpleFileType(Enum):
    UNKNOWN = "unknown"
    C_SOURCE = "cSource"
    CPP_SOURCE = "cppSource"
    ASM_SOURCE = "asmSource"
    VHDL_SOURCE = "vhdlSource"
    VHDL_SOURCE_87 = "vhdlSource-87"
    VHDL_SOURCE_93 = "vhdlSource-93"
    VERILOG_SOURCE = "verilogSource"
    VERILOG_SOURCE_95 = "verilogSource-95"
    VERILOG_SOURCE_2001 = "verilogSource-2001"
    SW_OBJECT = "swObject"
    SW_OBJECT_LIBRARY = "swObjectLibrary"
    VHDL_BINARY_LIBRARY = "vhdlBinaryLibrary"
    VERILOG_BINARY_LIBRARY = "verilogBinaryLibrary"
    UNELABORATED_HDL = "unelaboratedHdl"
    EXECUTABLE_HDL = "executableHdl"
    SYSTEM_VERILOG_SOURCE = "systemVerilogSource"
    SYSTEM_VERILOG_SOURCE_3_0 = "systemVerilogSource-3.0"
    SYSTEM_VERILOG_SOURCE_3_1 = "systemVerilogSource-3.1"
    SYSTEM_CSOURCE = "systemCSource"
    SYSTEM_CSOURCE_2_0 = "systemCSource-2.0"
    SYSTEM_CSOURCE_2_0_1 = "systemCSource-2.0.1"
    SYSTEM_CSOURCE_2_1 = "systemCSource-2.1"
    SYSTEM_CSOURCE_2_2 = "systemCSource-2.2"
    VERA_SOURCE = "veraSource"
    E_SOURCE = "eSource"
    PERL_SOURCE = "perlSource"
    TCL_SOURCE = "tclSource"
    OVASOURCE = "OVASource"
    SVASOURCE = "SVASource"
    PSL_SOURCE = "pslSource"
    SYSTEM_VERILOG_SOURCE_3_1A = "systemVerilogSource-3.1a"
    SDC = "SDC"
    VHDL_AMS_SOURCE = "vhdlAmsSource"
    VERILOG_AMS_SOURCE = "verilogAmsSource"
    SYSTEM_CAMS_SOURCE = "systemCAmsSource"
    LIBERTY_SOURCE = "libertySource"
    USER = "user"


class SimplePortAccessType(Enum):
    REF = "ref"
    PTR = "ptr"


class SimpleTiedValueTypeValue(Enum):
    OPEN = "open"
    DEFAULT = "default"


class SimpleWhiteboxType(Enum):
    SIGNAL = "signal"
    PIN = "pin"
    INTERFACE = "interface"


class TestableTestConstraint(Enum):
    UNCONSTRAINED = "unconstrained"
    RESTORE = "restore"
    WRITE_AS_READ = "writeAsRead"
    READ_ONLY = "readOnly"


class TransportMethodType(Enum):
    FILE = "file"


class UsageType(Enum):
    """
    Describes the usage of an address block.

    :cvar MEMORY: Denotes an address range that can be used for read-
        write or read-only data storage.
    :cvar REGISTER: Denotes an address block that is used to communicate
        with hardware.
    :cvar RESERVED: Denotes an address range that must remain
        unoccupied.
    """

    MEMORY = "memory"
    REGISTER = "register"
    RESERVED = "reserved"


@dataclass(kw_only=True)
class ValueMaskConfigType:
    """
    This type is used to specify a value and optional mask that are
    configurable.
    """

    class Meta:
        name = "valueMaskConfigType"


@dataclass(kw_only=True)
class VendorExtensions:
    """
    Container for vendor specific extensions.

    :ivar any_element: Accepts any element(s) the content provider wants
        to put here, including elements from the ipxact namespace.
    """

    class Meta:
        name = "vendorExtensions"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    any_element: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Wildcard",
            "namespace": "##any",
        },
    )


@dataclass(kw_only=True)
class ViewRef:
    class Meta:
        name = "viewRef"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    value: str = field(default="")
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )


@dataclass(kw_only=True)
class Volatile:
    """
    Indicates whether the data is volatile.
    """

    class Meta:
        name = "volatile"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    value: bool = field(default=False)


@dataclass(kw_only=True)
class WireTypeDef:
    """
    Definition of a single wire type defintion that can relate to multiple
    views.

    :ivar type_name: The name of the logic type. Examples could be
        std_logic, std_ulogic, std_logic_vector, sc_logic, ...
    :ivar type_definition: Where the definition of the type is
        contained. For std_logic, this is contained in
        IEEE.std_logic_1164.all. For sc_logic, this is contained in
        systemc.h. For VHDL this is the library and package as defined
        by the "used" statement. For SystemC and SystemVerilog it is the
        include file required. For verilog this is not needed.
    :ivar view_ref: A reference to a view name in the file for which
        this type applies.
    :ivar id:
    """

    class Meta:
        name = "wireTypeDef"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    type_name: None | WireTypeDef.TypeName = field(
        default=None,
        metadata={
            "name": "typeName",
            "type": "Element",
        },
    )
    type_definition: list[WireTypeDef.TypeDefinition] = field(
        default_factory=list,
        metadata={
            "name": "typeDefinition",
            "type": "Element",
        },
    )
    view_ref: list[WireTypeDef.ViewRef] = field(
        default_factory=list,
        metadata={
            "name": "viewRef",
            "type": "Element",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )

    @dataclass(kw_only=True)
    class TypeName:
        """
        :ivar value:
        :ivar constrained: Defines that the type for the port has
            constrainted the number of bits in the vector
        """

        value: str = field(default="")
        constrained: bool = field(
            default=False,
            metadata={
                "type": "Attribute",
            },
        )

    @dataclass(kw_only=True)
    class TypeDefinition:
        value: str = field(default="")
        id: None | str = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.w3.org/XML/1998/namespace",
            },
        )

    @dataclass(kw_only=True)
    class ViewRef:
        value: str = field(default="")
        id: None | str = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.w3.org/XML/1998/namespace",
            },
        )


@dataclass(kw_only=True)
class Access:
    """
    Indicates the accessibility of the data in the address bank, address
    block, register or field.

    Possible values are 'read-write', 'read-only', 'write-only',
    'writeOnce' and 'read-writeOnce'. If not specified the value is
    inherited from the containing object.
    """

    class Meta:
        name = "access"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    value: AccessType = field()


@dataclass(kw_only=True)
class CellSpecification:
    """
    Used to provide a generic description of a technology library cell.

    :ivar cell_function: Defines a technology library cell in library
        independent fashion, based on specification of a cell function
        and strength.
    :ivar cell_class: Defines a technology library cell in library
        independent fashion, based on specification of a cell class and
        strength.
    :ivar cell_strength: Indicates the desired strength of the specified
        cell.
    """

    class Meta:
        name = "cellSpecification"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    cell_function: None | CellSpecification.CellFunction = field(
        default=None,
        metadata={
            "name": "cellFunction",
            "type": "Element",
        },
    )
    cell_class: None | CellClassValueType = field(
        default=None,
        metadata={
            "name": "cellClass",
            "type": "Element",
        },
    )
    cell_strength: None | CellStrengthValueType = field(
        default=None,
        metadata={
            "name": "cellStrength",
            "type": "Attribute",
        },
    )

    @dataclass(kw_only=True)
    class CellFunction:
        value: CellFunctionValueType = field()
        other: None | str = field(
            default=None,
            metadata={
                "type": "Attribute",
            },
        )


@dataclass(kw_only=True)
class Choices:
    """
    Choices used by elements with an attribute ipxact:choiceRef.

    :ivar choice: Non-empty set of legal values for a elements with an
        attribute ipxact:choiceRef.
    """

    class Meta:
        name = "choices"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    choice: list[Choices.Choice] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "min_occurs": 1,
        },
    )

    @dataclass(kw_only=True)
    class Choice:
        """
        :ivar name: Choice key, available for reference by the
            ipxact:choiceRef attribute.
        :ivar enumeration: One possible value of ipxact:choice
        :ivar id:
        """

        name: str = field(
            metadata={
                "type": "Element",
            }
        )
        enumeration: list[Choices.Choice.Enumeration] = field(
            default_factory=list,
            metadata={
                "type": "Element",
                "min_occurs": 1,
            },
        )
        id: None | str = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.w3.org/XML/1998/namespace",
            },
        )

        @dataclass(kw_only=True)
        class Enumeration(ComplexBaseExpression):
            """
            :ivar text: When specified, displayed in place of the
                ipxact:enumeration value
            :ivar help: Text that may be displayed if the user requests
                help about the meaning of an element
            :ivar id:
            """

            text: None | str = field(
                default=None,
                metadata={
                    "type": "Attribute",
                },
            )
            help: None | str = field(
                default=None,
                metadata={
                    "type": "Attribute",
                },
            )
            id: None | str = field(
                default=None,
                metadata={
                    "type": "Attribute",
                    "namespace": "http://www.w3.org/XML/1998/namespace",
                },
            )


@dataclass(kw_only=True)
class ComplexBitSteeringExpression:
    """
    Indicates whether bit steering should be used to map this interface
    onto a bus of different data width.

    Values are "on", "off" or an expression which resolves to an
    unsigned-bit where a '1' indicates "on" and a '0' indicates "off"
    (defaults to "off").
    """

    class Meta:
        name = "complexBitSteeringExpression"

    value: str | SimpleBitSteeringExpressionValue = field(
        default="",
        metadata={
            "white_space": "collapse",
        },
    )
    other_attributes: dict[str, str] = field(
        default_factory=dict,
        metadata={
            "type": "Attributes",
            "namespace": "##other",
        },
    )


@dataclass(kw_only=True)
class ComplexTiedValueType:
    """
    An unsigned longint expression that resolves to the value set {0, 1,
    ...} or open or default.

    It is derived from longintExpression and it supports an expression
    value.

    :ivar value:
    :ivar other_attributes:
    :ivar minimum: For elements which can be specified using expression
        which are supposed to be resolved to a long value, this
        indicates the minimum value allowed.
    :ivar maximum: For elements which can be specified using expression
        which are supposed to be resolved to a long value, this
        indicates the maximum value allowed.
    """

    class Meta:
        name = "complexTiedValueType"

    value: str | SimpleTiedValueTypeValue = field(
        default="",
        metadata={
            "white_space": "collapse",
        },
    )
    other_attributes: dict[str, str] = field(
        default_factory=dict,
        metadata={
            "type": "Attributes",
            "namespace": "##other",
        },
    )
    minimum: None | int = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    maximum: None | int = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class ConfigurableElementValue(ComplexBaseExpression):
    """
    Describes the content of a configurable element.

    The required referenceId attribute refers to the ID attribute of the
    configurable element.

    :ivar reference_id: Refers to the ID attribute of the configurable
        element.
    :ivar id:
    """

    class Meta:
        name = "configurableElementValue"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    reference_id: str = field(
        metadata={
            "name": "referenceId",
            "type": "Attribute",
        }
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )


@dataclass(kw_only=True)
class Dependency(IpxactUri):
    """
    Specifies a location on which files or fileSets may be dependent.

    Typically, this would be a directory that would contain included files.
    """

    class Meta:
        name = "dependency"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )


@dataclass(kw_only=True)
class FileType:
    """
    Enumerated file types known by IP-XACT.
    """

    class Meta:
        name = "fileType"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    value: SimpleFileType = field()
    user: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )


@dataclass(kw_only=True)
class GroupSelector:
    """
    Specifies a set of group names used to select subsequent generators.

    The attribute "multipleGroupOperator" specifies the OR or AND selection
    operator if there is more than one group name (default=OR).

    :ivar name: Specifies a generator group name or a generator chain
        group name to be selected for inclusion in the generator chain.
    :ivar multiple_group_selection_operator: Specifies the OR or AND
        selection operator if there is more than one group name.
    :ivar id:
    """

    class Meta:
        name = "groupSelector"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    name: list[GroupSelector.Name] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "min_occurs": 1,
        },
    )
    multiple_group_selection_operator: GroupSelectorMultipleGroupSelectionOperator = field(
        default=GroupSelectorMultipleGroupSelectionOperator.OR,
        metadata={
            "name": "multipleGroupSelectionOperator",
            "type": "Attribute",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )

    @dataclass(kw_only=True)
    class Name:
        value: str = field(default="")
        id: None | str = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.w3.org/XML/1998/namespace",
            },
        )


@dataclass(kw_only=True)
class HierInterface(InterfaceType):
    """
    Hierarchical reference to an interface.

    :ivar path: A decending hierarchical (slash separated - example
        x/y/z) path to the component instance containing the specified
        component instance in componentRef. If not specified the
        componentRef instance shall exist in the current design.
    """

    class Meta:
        name = "hierInterface"

    path: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "white_space": "collapse",
            "pattern": r"\i[\p{L}\p{N}\.\-:_]*|\i[\p{L}\p{N}\.\-:_]*/\i[\p{L}\p{N}\.\-:_]*|(\i[\p{L}\p{N}\.\-:_]*/)+[\i\p{L}\p{N}\.\-:_]*",
        },
    )


@dataclass(kw_only=True)
class Initiative:
    """
    If this element is present, the type of access is restricted to the
    specified value.
    """

    class Meta:
        name = "initiative"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    value: InitiativeType = field()


@dataclass(kw_only=True)
class Kind:
    """
    Defines the protocol type.

    Defaults to tlm_base_protocol_type for TLM sockets.
    """

    class Meta:
        name = "kind"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    value: KindType = field()
    custom: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class MemoryMapRef(MemoryMapRefType):
    """
    References the memory map.

    The name of the memory map is kept in its memoryMapRef attribute.
    """

    class Meta:
        name = "memoryMapRef"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"


@dataclass(kw_only=True)
class MonitorInterfaceType(InterfaceType):
    """
    Hierarchical reference to an interface being monitored or monitoring
    another interface.

    :ivar description:
    :ivar vendor_extensions:
    :ivar path: A decending hierarchical (slash separated - example
        x/y/z) path to the component instance containing the specified
        component instance in componentRef. If not specified the
        componentRef instance shall exist in the current design.
    """

    class Meta:
        name = "monitorInterfaceType"

    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    path: None | object = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class Payload:
    """
    defines the structure of data transported by this port.

    :ivar name: Defines the name of the payload. For example: TLM2 or
        TLM1
    :ivar type_value: Defines the type of the payload.
    :ivar extension: Defines the name of the payload extension. If
        attribute is not specified, it is by default optional.
    :ivar vendor_extensions:
    """

    class Meta:
        name = "payload"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    name: None | str = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    type_value: PayloadType = field(
        metadata={
            "name": "type",
            "type": "Element",
        }
    )
    extension: None | Payload.Extension = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
        },
    )

    @dataclass(kw_only=True)
    class Extension:
        """
        :ivar value:
        :ivar mandatory: True if the payload extension is mandatory.
        """

        value: str = field(default="")
        mandatory: bool = field(
            default=False,
            metadata={
                "type": "Attribute",
            },
        )


@dataclass(kw_only=True)
class PortAccessType:
    """
    Indicates how a netlister accesses a port. 'ref' means accessed by
    reference (default) and 'ptr' means accessed by pointer.
    """

    class Meta:
        name = "portAccessType"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    value: SimplePortAccessType = field()


@dataclass(kw_only=True)
class Presence:
    """
    If this element is present, the existance of the port is controlled by
    the specified value. valid values are 'illegal', 'required' and
    'optional'.
    """

    class Meta:
        name = "presence"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    value: PresenceType = field(default=PresenceType.OPTIONAL)


@dataclass(kw_only=True)
class RealExpression(ComplexBaseExpression):
    """
    A real which supports an expression value.

    :ivar minimum: For elements which can be specified using expression
        which are supposed to be resolved to a real value, this
        indicates the minimum value allowed.
    :ivar maximum: For elements which can be specified using expression
        which are supposed to be resolved to a real value, this
        indicates the maximum value allowed.
    """

    class Meta:
        name = "realExpression"

    minimum: None | float = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    maximum: None | float = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class RequiresDriver:
    """
    Specifies if a port requires a driver.

    Default is false. The attribute driverType can further qualify what
    type of driver is required. Undefined behaviour if direction is not
    input or inout. Driver type any indicates that any unspecified type of
    driver must be connected.

    :ivar value:
    :ivar driver_type: Defines the type of driver that is required. The
        default is any type of driver. The 2 other options are a clock
        type driver or a singleshot type driver.
    """

    class Meta:
        name = "requiresDriver"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    value: bool = field(default=False)
    driver_type: RequiresDriverDriverType = field(
        default=RequiresDriverDriverType.ANY,
        metadata={
            "name": "driverType",
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class SignedIntExpression(ComplexBaseExpression):
    """
    A signed int which supports an expression value.

    :ivar minimum: For elements which can be specified using expression
        which are supposed to be resolved to a long value, this
        indicates the minimum value allowed.
    :ivar maximum: For elements which can be specified using expression
        which are supposed to be resolved to a long value, this
        indicates the maximum value allowed.
    """

    class Meta:
        name = "signedIntExpression"

    minimum: None | int = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    maximum: None | int = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class SignedLongintExpression(ComplexBaseExpression):
    """
    An unsigned longint which supports an expression value.

    :ivar minimum: For elements which can be specified using expression
        which are supposed to be resolved to a signed longint value,
        this indicates the minimum value allowed.
    :ivar maximum: For elements which can be specified using expression
        which are supposed to be resolved to a signed longint value,
        this indicates the maximum value allowed.
    """

    class Meta:
        name = "signedLongintExpression"

    minimum: None | int = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    maximum: None | int = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class StringExpression(ComplexBaseExpression):
    """
    Represents a string.

    It supports an expression value.
    """

    class Meta:
        name = "stringExpression"


@dataclass(kw_only=True)
class StringUriexpression(ComplexBaseExpression):
    """
    IP-XACT URI, like a standard xs:anyURI except that it can contain
    environment variables in the ${ } form, to be replaced by their value
    to provide the underlying URI.
    """

    class Meta:
        name = "stringURIExpression"


@dataclass(kw_only=True)
class TimingConstraint:
    """
    Defines a timing constraint for the associated port.

    The constraint is relative to the clock specified by the clockName
    attribute. The clockEdge indicates which clock edge the constraint is
    associated with (default is rising edge). The delayType attribute can
    be specified to further refine the constraint.

    :ivar value:
    :ivar clock_edge: Indicates the clock edge that a timing constraint
        is relative to.
    :ivar delay_type: Indicates the type of delay in a timing constraint
        - minimum or maximum.
    :ivar clock_name: Indicates the name of the clock to which this
        constraint applies.
    :ivar id:
    """

    class Meta:
        name = "timingConstraint"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    value: float = field(
        metadata={
            "min_inclusive": 0.0,
            "max_inclusive": 100.0,
        }
    )
    clock_edge: None | EdgeValueType = field(
        default=None,
        metadata={
            "name": "clockEdge",
            "type": "Attribute",
        },
    )
    delay_type: None | DelayValueType = field(
        default=None,
        metadata={
            "name": "delayType",
            "type": "Attribute",
        },
    )
    clock_name: str = field(
        metadata={
            "name": "clockName",
            "type": "Attribute",
            "white_space": "collapse",
            "pattern": r"\i[\p{L}\p{N}\.\-:_]*",
        }
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )


@dataclass(kw_only=True)
class UnsignedBitExpression(ComplexBaseExpression):
    """
    Represents a single-bit/bool.

    It supports an expression value.
    """

    class Meta:
        name = "unsignedBitExpression"


@dataclass(kw_only=True)
class UnsignedBitVectorExpression(ComplexBaseExpression):
    """
    Represents a bit-string.

    It supports an expression value.
    """

    class Meta:
        name = "unsignedBitVectorExpression"


@dataclass(kw_only=True)
class UnsignedIntExpression(ComplexBaseExpression):
    """
    An unsigned int which supports an expression value.

    :ivar minimum: For elements which can be specified using expression
        which are supposed to be resolved to an unsiged int value, this
        indicates the minimum value allowed.
    :ivar maximum: For elements which can be specified using expression
        which are supposed to be resolved to a unsigned int value, this
        indicates the maximum value allowed.
    """

    class Meta:
        name = "unsignedIntExpression"

    minimum: None | int = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    maximum: None | int = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class UnsignedLongintExpression(ComplexBaseExpression):
    """
    An unsigned longint which supports an expression value.

    :ivar minimum: For elements which can be specified using expression
        which are supposed to be resolved to a unsigend longint value,
        this indicates the minimum value allowed.
    :ivar maximum: For elements which can be specified using expression
        which are supposed to be resolved to an unsigend longint value,
        this indicates the maximum value allowed.
    """

    class Meta:
        name = "unsignedLongintExpression"

    minimum: None | int = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    maximum: None | int = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class UnsignedPositiveIntExpression(ComplexBaseExpression):
    """
    An positive unsigned int which supports an expression value.

    :ivar minimum: For elements which can be specified using expression
        which are supposed to be resolved to an unsiged int value, this
        indicates the minimum value allowed.
    :ivar maximum: For elements which can be specified using expression
        which are supposed to be resolved to a unsigned int value, this
        indicates the maximum value allowed.
    """

    class Meta:
        name = "unsignedPositiveIntExpression"

    minimum: None | int = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    maximum: None | int = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class UnsignedPositiveLongintExpression(ComplexBaseExpression):
    """
    A positive unsigned longint which supports an expression value.

    :ivar minimum: For elements which can be specified using expression
        which are supposed to be resolved to a positive unsigned longint
        value, this indicates the minimum value allowed.
    :ivar maximum: For elements which can be specified using expression
        which are supposed to be resolved to a positive unsigned longint
        value, this indicates the maximum value allowed.
    """

    class Meta:
        name = "unsignedPositiveLongintExpression"

    minimum: None | int = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    maximum: None | int = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class WireTypeDefs:
    """
    The group of wire type definitions.

    If no match to a viewName is found then the default language types are
    to be used. See the User Guide for these default types.
    """

    class Meta:
        name = "wireTypeDefs"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    wire_type_def: list[WireTypeDef] = field(
        default_factory=list,
        metadata={
            "name": "wireTypeDef",
            "type": "Element",
            "min_occurs": 1,
        },
    )


@dataclass(kw_only=True)
class ActiveCondition(UnsignedBitExpression):
    """
    Expression that determines whether the enclosing element responds to
    read or write accesses to its specified address location.

    The expression can include dynamic values referencing register/field
    values and component states. If it evaluates to true, then the
    enclosing register can be accessed per its mapping and access
    specification. If it evaluates to false, the enclosing register/field
    cannot be accessed. If a register does not include an activeCondition
    or alternateRegister(s), then the register is uncondiitionally
    accessible. If a register does not include an activeCondition, but does
    include alternateRegister(s), then the condition that determines which
    is accessible is considered unspecified.
    """

    class Meta:
        name = "activeCondition"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"


@dataclass(kw_only=True)
class AddressUnitBits(UnsignedPositiveLongintExpression):
    """
    The number of data bits in an addressable unit.

    The default is byte addressable (8 bits).
    """

    class Meta:
        name = "addressUnitBits"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"


@dataclass(kw_only=True)
class Assertion:
    """
    Provides an expression for describing valid parameter value settings.

    If a assertion assert expression evaluates false, the name, displayName
    and/or description can be used to communicate the assertion failure.

    :ivar name: Unique name
    :ivar display_name:
    :ivar description:
    :ivar assert_value:
    :ivar id:
    """

    class Meta:
        name = "assertion"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    name: str = field(
        metadata={
            "type": "Element",
        }
    )
    display_name: None | DisplayName = field(
        default=None,
        metadata={
            "name": "displayName",
            "type": "Element",
        },
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    assert_value: UnsignedBitExpression = field(
        metadata={
            "name": "assert",
            "type": "Element",
        }
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )


@dataclass(kw_only=True)
class BaseAddress(UnsignedLongintExpression):
    """
    Base of an address block, bank, subspace map or address space.

    Expressed as the number of addressable units from the containing
    memoryMap or localMemoryMap.
    """

    class Meta:
        name = "baseAddress"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"


@dataclass(kw_only=True)
class BitsInLau(UnsignedPositiveLongintExpression):
    """
    The number of bits in the least addressable unit.

    The default is byte addressable (8 bits).
    """

    class Meta:
        name = "bitsInLau"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"


@dataclass(kw_only=True)
class BusWidth(UnsignedIntExpression):
    """
    defines the bus size in bits.

    This can be the result of an expression.
    """

    class Meta:
        name = "busWidth"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"


@dataclass(kw_only=True)
class ClockDriverType:
    """
    :ivar clock_period: Clock period in units defined by the units
        attribute. Default is nanoseconds.
    :ivar clock_pulse_offset: Time until first pulse. Units are defined
        by the units attribute. Default is nanoseconds.
    :ivar clock_pulse_value: Value of port after first clock edge.
    :ivar clock_pulse_duration: Duration of first state in cycle. Units
        are defined by the units attribute. Default is nanoseconds.
    :ivar id:
    """

    class Meta:
        name = "clockDriverType"

    clock_period: ClockDriverType.ClockPeriod = field(
        metadata={
            "name": "clockPeriod",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    clock_pulse_offset: ClockDriverType.ClockPulseOffset = field(
        metadata={
            "name": "clockPulseOffset",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    clock_pulse_value: UnsignedBitVectorExpression = field(
        metadata={
            "name": "clockPulseValue",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    clock_pulse_duration: ClockDriverType.ClockPulseDuration = field(
        metadata={
            "name": "clockPulseDuration",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )

    @dataclass(kw_only=True)
    class ClockPeriod(RealExpression):
        units: DelayValueUnitType = field(
            default=DelayValueUnitType.NS,
            metadata={
                "type": "Attribute",
            },
        )

    @dataclass(kw_only=True)
    class ClockPulseOffset(RealExpression):
        units: DelayValueUnitType = field(
            default=DelayValueUnitType.NS,
            metadata={
                "type": "Attribute",
            },
        )

    @dataclass(kw_only=True)
    class ClockPulseDuration(RealExpression):
        units: DelayValueUnitType = field(
            default=DelayValueUnitType.NS,
            metadata={
                "type": "Attribute",
            },
        )


@dataclass(kw_only=True)
class ConfigurableElementValues:
    """
    All configuration information for a contained component, generator,
    generator chain or abstractor instance.

    :ivar configurable_element_value: Describes the content of a
        configurable element. The required referenceId attribute refers
        to the ID attribute of the configurable element.
    """

    class Meta:
        name = "configurableElementValues"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    configurable_element_value: list[ConfigurableElementValue] = field(
        default_factory=list,
        metadata={
            "name": "configurableElementValue",
            "type": "Element",
            "min_occurs": 1,
        },
    )


@dataclass(kw_only=True)
class DefaultValue(UnsignedBitVectorExpression):
    """
    Default value for a wire port.
    """

    class Meta:
        name = "defaultValue"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"


@dataclass(kw_only=True)
class DriveConstraint:
    """
    Defines a constraint indicating how an input is to be driven.

    The preferred methodology is to specify a library cell in technology
    independent fashion. The implemention tool should assume that the
    associated port is driven by the specified cell, or that the drive
    strength of the input port is indicated by the specified resistance
    value.
    """

    class Meta:
        name = "driveConstraint"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    cell_specification: CellSpecification = field(
        metadata={
            "name": "cellSpecification",
            "type": "Element",
        }
    )


@dataclass(kw_only=True)
class EnumeratedValues:
    """
    Enumerates specific values that can be assigned to the bit field.

    :ivar enumerated_value: Enumerates specific values that can be
        assigned to the bit field. The name of this enumerated value.
        This may be used as a token in generating code.
    """

    class Meta:
        name = "enumeratedValues"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    enumerated_value: list[EnumeratedValues.EnumeratedValue] = field(
        default_factory=list,
        metadata={
            "name": "enumeratedValue",
            "type": "Element",
            "min_occurs": 1,
        },
    )

    @dataclass(kw_only=True)
    class EnumeratedValue:
        """
        :ivar name: Unique name
        :ivar display_name:
        :ivar description:
        :ivar value: Enumerated bit field value.
        :ivar vendor_extensions:
        :ivar usage: Usage for the enumeration. 'read' for a software
            read access. 'write' for a software write access. 'read-
            write' for a software read or write access.
        :ivar id:
        """

        name: str = field(
            metadata={
                "type": "Element",
            }
        )
        display_name: None | DisplayName = field(
            default=None,
            metadata={
                "name": "displayName",
                "type": "Element",
            },
        )
        description: None | Description = field(
            default=None,
            metadata={
                "type": "Element",
            },
        )
        value: UnsignedBitVectorExpression = field(
            metadata={
                "type": "Element",
            }
        )
        vendor_extensions: None | VendorExtensions = field(
            default=None,
            metadata={
                "name": "vendorExtensions",
                "type": "Element",
            },
        )
        usage: EnumeratedValueUsage = field(
            default=EnumeratedValueUsage.READ_WRITE,
            metadata={
                "type": "Attribute",
            },
        )
        id: None | str = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.w3.org/XML/1998/namespace",
            },
        )


@dataclass(kw_only=True)
class FileBuilderType:
    """
    :ivar file_type:
    :ivar command: Default command used to build files of the specified
        fileType.
    :ivar flags: Flags given to the build command when building files of
        this type.
    :ivar replace_default_flags: If true, replace any default flags
        value with the value in the sibling flags element. Otherwise,
        append the contents of the sibling flags element to any default
        flags value. If the value is true and the "flags" element is
        empty or missing, this will have the result of clearing any
        default flags value.
    :ivar id:
    """

    class Meta:
        name = "fileBuilderType"

    file_type: FileType = field(
        metadata={
            "name": "fileType",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    command: None | StringExpression = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    flags: None | StringExpression = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    replace_default_flags: None | UnsignedBitExpression = field(
        default=None,
        metadata={
            "name": "replaceDefaultFlags",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )


@dataclass(kw_only=True)
class GeneratorSelectorType:
    class Meta:
        name = "generatorSelectorType"

    group_selector: GroupSelector = field(
        metadata={
            "name": "groupSelector",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )


@dataclass(kw_only=True)
class IndicesType:
    """
    :ivar index: An index into an object in the referenced view.
    """

    class Meta:
        name = "indicesType"

    index: list[UnsignedIntExpression] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            "min_occurs": 1,
        },
    )


@dataclass(kw_only=True)
class IpxactFileType:
    """
    :ivar vlnv: VLNV of the IP-XACT file being cataloged.
    :ivar name: Name of the IP-XACT file being cataloged.
    :ivar description:
    :ivar vendor_extensions:
    """

    class Meta:
        name = "ipxactFileType"

    vlnv: LibraryRefType = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    name: StringUriexpression = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )


@dataclass(kw_only=True)
class IsPresent(UnsignedBitExpression):
    """
    Expression that determines whether the enclosing element should be
    treated as present (expression evaluates to "true") or disregarded
    (expression evalutes to "false").
    """

    class Meta:
        name = "isPresent"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"


@dataclass(kw_only=True)
class IsResetType(UnsignedBitExpression):
    """
    If this evaluates to true, it indicates this port triggers the reset of
    registers and fields, if not present its value is assumed to be false.

    The resetTypeRef attribute indicates the triggered reset event.

    :ivar reset_type_ref: Reference to a user defined resetType. Assumed
        to be HARD if not present.
    :ivar id:
    """

    class Meta:
        name = "isResetType"

    reset_type_ref: None | str = field(
        default=None,
        metadata={
            "name": "resetTypeRef",
            "type": "Attribute",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )


@dataclass(kw_only=True)
class Left(UnsignedIntExpression):
    """
    The optional element left specifies the left boundary.
    """

    class Meta:
        name = "left"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"


@dataclass(kw_only=True)
class LinkerCommandFile:
    """
    Specifies a linker command file.

    :ivar name: Linker command file name.
    :ivar command_line_switch: The command line switch to specify the
        linker command file.
    :ivar enable: Specifies whether to generate and enable the linker
        command file.
    :ivar generator_ref:
    :ivar vendor_extensions:
    """

    class Meta:
        name = "linkerCommandFile"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    name: StringUriexpression = field(
        metadata={
            "type": "Element",
        }
    )
    command_line_switch: StringExpression = field(
        metadata={
            "name": "commandLineSwitch",
            "type": "Element",
        }
    )
    enable: UnsignedBitExpression = field(
        metadata={
            "type": "Element",
        }
    )
    generator_ref: list[GeneratorRef] = field(
        default_factory=list,
        metadata={
            "name": "generatorRef",
            "type": "Element",
        },
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
        },
    )


@dataclass(kw_only=True)
class LoadConstraint:
    """
    Defines a constraint indicating the type of load on an output port.

    :ivar cell_specification:
    :ivar count: Indicates how many loads of the specified cell are
        connected. If not present, 3 is assumed.
    """

    class Meta:
        name = "loadConstraint"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    cell_specification: CellSpecification = field(
        metadata={
            "name": "cellSpecification",
            "type": "Element",
        }
    )
    count: None | UnsignedPositiveIntExpression = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )


@dataclass(kw_only=True)
class Phase(RealExpression):
    """
    This is an non-negative floating point number that is used to sequence
    when a generator is run.

    The generators are run in order starting with zero. There may be
    multiple generators with the same phase number. In this case, the order
    should not matter with respect to other generators at the same phase.
    If no phase number is given the generator will be considered in the
    "last" phase and these generators will be run in the order in which
    they are encountered while processing generator elements.
    """

    class Meta:
        name = "phase"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"


@dataclass(kw_only=True)
class Protocol:
    """
    defines the protocol type.

    Defaults to tlm_base_protocol_type for TLM sockets.
    """

    class Meta:
        name = "protocol"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    protocol_type: Protocol.ProtocolType = field(
        metadata={
            "name": "protocolType",
            "type": "Element",
        }
    )
    payload: None | Payload = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )

    @dataclass(kw_only=True)
    class ProtocolType:
        value: ProtocolTypeType = field()
        custom: None | str = field(
            default=None,
            metadata={
                "type": "Attribute",
            },
        )


@dataclass(kw_only=True)
class RemapStates:
    """
    Contains a list of remap state names and associated port values.

    :ivar remap_state: Contains a list of ports and values in remapPort
        and a list of registers and values that when all evaluate to
        true which tell the decoder to enter this remap state. The name
        attribute identifies the name of the state. If a list of
        remapPorts and/or remapRegisters is not defined then the
        condition for that state cannot be defined.
    """

    class Meta:
        name = "remapStates"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    remap_state: list[RemapStates.RemapState] = field(
        default_factory=list,
        metadata={
            "name": "remapState",
            "type": "Element",
            "min_occurs": 1,
        },
    )

    @dataclass(kw_only=True)
    class RemapState:
        """
        :ivar name: Unique name
        :ivar display_name:
        :ivar description:
        :ivar remap_ports: List of ports and their values that shall
            invoke this remap state.
        """

        name: str = field(
            metadata={
                "type": "Element",
            }
        )
        display_name: None | DisplayName = field(
            default=None,
            metadata={
                "name": "displayName",
                "type": "Element",
            },
        )
        description: None | Description = field(
            default=None,
            metadata={
                "type": "Element",
            },
        )
        remap_ports: None | RemapStates.RemapState.RemapPorts = field(
            default=None,
            metadata={
                "name": "remapPorts",
                "type": "Element",
            },
        )

        @dataclass(kw_only=True)
        class RemapPorts:
            """
            :ivar remap_port: Contains the name and value of a port on
                the component, the value indicates the logic value which
                this port must take to effect the remapping. The
                portMapRef attribute stores the name of the port which
                takes that value.
            """

            remap_port: list[RemapStates.RemapState.RemapPorts.RemapPort] = (
                field(
                    default_factory=list,
                    metadata={
                        "name": "remapPort",
                        "type": "Element",
                        "min_occurs": 1,
                    },
                )
            )

            @dataclass(kw_only=True)
            class RemapPort:
                """
                :ivar port_index: Index for a vectored type port. Must
                    be a number between left and right for the port.
                :ivar value:
                :ivar port_ref: This attribute identifies a signal on
                    the component which affects the component's memory
                    layout
                """

                port_index: None | UnsignedIntExpression = field(
                    default=None,
                    metadata={
                        "name": "portIndex",
                        "type": "Element",
                    },
                )
                value: UnsignedIntExpression = field(
                    metadata={
                        "type": "Element",
                    }
                )
                port_ref: str = field(
                    metadata={
                        "name": "portRef",
                        "type": "Attribute",
                        "white_space": "collapse",
                        "pattern": r"\i[\p{L}\p{N}\.\-:_]*",
                    }
                )


@dataclass(kw_only=True)
class Reset:
    """
    Register value at reset.

    :ivar value: The value itself.
    :ivar mask: Mask to be anded with the value before comparing to the
        reset value.
    :ivar reset_type_ref: Reference to a user defined resetType. Assumed
        to be HARD if not present.
    :ivar id:
    """

    class Meta:
        name = "reset"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    value: UnsignedBitVectorExpression = field(
        metadata={
            "type": "Element",
        }
    )
    mask: None | UnsignedBitVectorExpression = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    reset_type_ref: None | str = field(
        default=None,
        metadata={
            "name": "resetTypeRef",
            "type": "Attribute",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )


@dataclass(kw_only=True)
class Right(UnsignedIntExpression):
    """
    The optional element right specifies the right boundary.
    """

    class Meta:
        name = "right"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"


@dataclass(kw_only=True)
class SingleShotDriver:
    """
    Describes a driven one-shot port.

    :ivar single_shot_offset: Time in nanoseconds until start of one-
        shot.
    :ivar single_shot_value: Value of port after first  edge of one-
        shot.
    :ivar single_shot_duration: Duration in nanoseconds of the one shot.
    """

    class Meta:
        name = "singleShotDriver"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    single_shot_offset: RealExpression = field(
        metadata={
            "name": "singleShotOffset",
            "type": "Element",
        }
    )
    single_shot_value: UnsignedBitVectorExpression = field(
        metadata={
            "name": "singleShotValue",
            "type": "Element",
        }
    )
    single_shot_duration: RealExpression = field(
        metadata={
            "name": "singleShotDuration",
            "type": "Element",
        }
    )


@dataclass(kw_only=True)
class Value(StringExpression):
    """
    The value of the parameter.
    """

    class Meta:
        name = "value"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"


@dataclass(kw_only=True)
class WriteValueConstraintType:
    """
    A constraint on the values that can be written to this field.

    Absence of this element implies that any value that fits can be written
    to it.

    :ivar write_as_read: writeAsRead indicates that only a value
        immediately read before a write is a legal value to be written.
    :ivar use_enumerated_values: useEnumeratedValues indicates that only
        write enumeration value shall be legal values to be written.
    :ivar minimum: The minimum legal value that may be written to a
        field
    :ivar maximum: The maximum legal value that may be written to a
        field
    """

    class Meta:
        name = "writeValueConstraintType"

    write_as_read: None | bool = field(
        default=None,
        metadata={
            "name": "writeAsRead",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    use_enumerated_values: None | bool = field(
        default=None,
        metadata={
            "name": "useEnumeratedValues",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    minimum: None | UnsignedBitVectorExpression = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    maximum: None | UnsignedBitVectorExpression = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )


@dataclass(kw_only=True)
class AbstractionDefPortConstraintsType:
    """
    Defines constraints that apply to a wire type port in an abstraction
    definition.
    """

    class Meta:
        name = "abstractionDefPortConstraintsType"

    timing_constraint: list[TimingConstraint] = field(
        default_factory=list,
        metadata={
            "name": "timingConstraint",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    drive_constraint: list[DriveConstraint] = field(
        default_factory=list,
        metadata={
            "name": "driveConstraint",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            "max_occurs": 2,
        },
    )
    load_constraint: list[LoadConstraint] = field(
        default_factory=list,
        metadata={
            "name": "loadConstraint",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            "max_occurs": 3,
        },
    )


@dataclass(kw_only=True)
class ActiveInterface(InterfaceType):
    """
    :ivar is_present:
    :ivar description:
    :ivar exclude_ports: The list of physical ports to be excluded from
        an interface based connection. Analogous to the removing the
        port map element for the named ports.
    :ivar vendor_extensions:
    """

    class Meta:
        name = "activeInterface"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    is_present: None | IsPresent = field(
        default=None,
        metadata={
            "name": "isPresent",
            "type": "Element",
        },
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    exclude_ports: None | ActiveInterface.ExcludePorts = field(
        default=None,
        metadata={
            "name": "excludePorts",
            "type": "Element",
        },
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
        },
    )

    @dataclass(kw_only=True)
    class ExcludePorts:
        """
        :ivar exclude_port: The name of a physical port to be excluded
            from the interface based connection.
        """

        exclude_port: list[ActiveInterface.ExcludePorts.ExcludePort] = field(
            default_factory=list,
            metadata={
                "name": "excludePort",
                "type": "Element",
                "min_occurs": 1,
            },
        )

        @dataclass(kw_only=True)
        class ExcludePort:
            value: str = field(
                default="",
                metadata={
                    "white_space": "collapse",
                    "pattern": r"\i[\p{L}\p{N}\.\-:_]*",
                },
            )
            id: None | str = field(
                default=None,
                metadata={
                    "type": "Attribute",
                    "namespace": "http://www.w3.org/XML/1998/namespace",
                },
            )


@dataclass(kw_only=True)
class AddrSpaceRefType:
    """
    Base type for an element which references an address space.

    Reference is kept in an attribute rather than the text value, so that
    the type may be extended with child elements if necessary.

    :ivar is_present:
    :ivar address_space_ref: A reference to a unique address space.
    :ivar id:
    """

    class Meta:
        name = "addrSpaceRefType"

    is_present: None | IsPresent = field(
        default=None,
        metadata={
            "name": "isPresent",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    address_space_ref: str = field(
        metadata={
            "name": "addressSpaceRef",
            "type": "Attribute",
        }
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )


@dataclass(kw_only=True)
class Assertions:
    """
    List of assertions about allowed parameter values.
    """

    class Meta:
        name = "assertions"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    assertion: list[Assertion] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )


@dataclass(kw_only=True)
class Channels:
    """
    Lists all channel connections between mirror interfaces of this
    component.

    :ivar channel: Defines a set of mirrored interfaces of this
        component that are connected to one another.
    """

    class Meta:
        name = "channels"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    channel: list[Channels.Channel] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "min_occurs": 1,
        },
    )

    @dataclass(kw_only=True)
    class Channel:
        """
        :ivar name: Unique name
        :ivar display_name:
        :ivar description:
        :ivar is_present:
        :ivar bus_interface_ref: Contains the name of one of the bus
            interfaces that is part of this channel. The ordering of the
            references may be important to the design environment.
        :ivar id:
        """

        name: str = field(
            metadata={
                "type": "Element",
            }
        )
        display_name: None | DisplayName = field(
            default=None,
            metadata={
                "name": "displayName",
                "type": "Element",
            },
        )
        description: None | Description = field(
            default=None,
            metadata={
                "type": "Element",
            },
        )
        is_present: None | IsPresent = field(
            default=None,
            metadata={
                "name": "isPresent",
                "type": "Element",
            },
        )
        bus_interface_ref: list[Channels.Channel.BusInterfaceRef] = field(
            default_factory=list,
            metadata={
                "name": "busInterfaceRef",
                "type": "Element",
                "min_occurs": 2,
            },
        )
        id: None | str = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.w3.org/XML/1998/namespace",
            },
        )

        @dataclass(kw_only=True)
        class BusInterfaceRef:
            local_name: str = field(
                metadata={
                    "name": "localName",
                    "type": "Element",
                }
            )
            is_present: None | IsPresent = field(
                default=None,
                metadata={
                    "name": "isPresent",
                    "type": "Element",
                },
            )
            id: None | str = field(
                default=None,
                metadata={
                    "type": "Attribute",
                    "namespace": "http://www.w3.org/XML/1998/namespace",
                },
            )


@dataclass(kw_only=True)
class ClockDriver(ClockDriverType):
    """
    Describes a driven clock port.

    :ivar clock_name: Indicates the name of the cllock. If not specified
        the name is assumed to be the name of the containing port.
    """

    class Meta:
        name = "clockDriver"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    clock_name: None | str = field(
        default=None,
        metadata={
            "name": "clockName",
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class ConfigurableArrays:
    """
    :ivar array: Specific left and right array bounds.
    """

    class Meta:
        name = "configurableArrays"

    array: list[ConfigurableArrays.Array] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            "min_occurs": 1,
        },
    )

    @dataclass(kw_only=True)
    class Array:
        left: Left = field(
            metadata={
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            }
        )
        right: Right = field(
            metadata={
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            }
        )
        id: None | str = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.w3.org/XML/1998/namespace",
            },
        )


@dataclass(kw_only=True)
class ConfigurableLibraryRefType:
    """
    Base IP-XACT document reference type for configurable top-level
    objects.

    Contains vendor, library, name and version attributes along with
    configurable element values.
    """

    class Meta:
        name = "configurableLibraryRefType"

    configurable_element_values: None | ConfigurableElementValues = field(
        default=None,
        metadata={
            "name": "configurableElementValues",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    vendor: str = field(
        metadata={
            "type": "Attribute",
        }
    )
    library: str = field(
        metadata={
            "type": "Attribute",
        }
    )
    name: str = field(
        metadata={
            "type": "Attribute",
        }
    )
    version: str = field(
        metadata={
            "type": "Attribute",
        }
    )


@dataclass(kw_only=True)
class ConstraintSet:
    """
    Defines constraints that apply to a component port.

    If multiple constraintSet elements are used, each must have a unique
    value for the constraintSetId attribute.

    :ivar name: Unique name
    :ivar display_name:
    :ivar description:
    :ivar vector: The optional element vector specify the bits of a
        vector for which the constraints apply. The vaules of left and
        right must be within the range of the port. If the vector is not
        specified then the constraints apply to all the bits of the
        port.
    :ivar drive_constraint:
    :ivar load_constraint:
    :ivar timing_constraint:
    :ivar constraint_set_id: Indicates a name for this set of
        constraints. Constraints are tied to a view using this name in
        the constraintSetRef element.
    :ivar id:
    """

    class Meta:
        name = "constraintSet"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    name: None | str = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    display_name: None | DisplayName = field(
        default=None,
        metadata={
            "name": "displayName",
            "type": "Element",
        },
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    vector: None | ConstraintSet.Vector = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    drive_constraint: None | DriveConstraint = field(
        default=None,
        metadata={
            "name": "driveConstraint",
            "type": "Element",
        },
    )
    load_constraint: None | LoadConstraint = field(
        default=None,
        metadata={
            "name": "loadConstraint",
            "type": "Element",
        },
    )
    timing_constraint: list[TimingConstraint] = field(
        default_factory=list,
        metadata={
            "name": "timingConstraint",
            "type": "Element",
        },
    )
    constraint_set_id: str = field(
        default="default",
        metadata={
            "name": "constraintSetId",
            "type": "Attribute",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )

    @dataclass(kw_only=True)
    class Vector:
        """
        :ivar left: The optional elements left and right can be used to
            select a bit-slice of a vector.
        :ivar right: The optional elements left and right can be used to
            select a bit-slice of a vector.
        """

        left: UnsignedIntExpression = field(
            metadata={
                "type": "Element",
            }
        )
        right: UnsignedIntExpression = field(
            metadata={
                "type": "Element",
            }
        )


@dataclass(kw_only=True)
class ConstraintSetRef:
    """
    A reference to a set of port constraints.
    """

    class Meta:
        name = "constraintSetRef"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    local_name: str = field(
        metadata={
            "name": "localName",
            "type": "Element",
        }
    )
    is_present: None | IsPresent = field(
        default=None,
        metadata={
            "name": "isPresent",
            "type": "Element",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )


@dataclass(kw_only=True)
class FileSetRef:
    """
    A reference to a fileSet.

    :ivar local_name: Refers to a fileSet defined within this
        description.
    :ivar is_present:
    :ivar id:
    """

    class Meta:
        name = "fileSetRef"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    local_name: str = field(
        metadata={
            "name": "localName",
            "type": "Element",
        }
    )
    is_present: None | IsPresent = field(
        default=None,
        metadata={
            "name": "isPresent",
            "type": "Element",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )


@dataclass(kw_only=True)
class HierInterfaceType:
    """
    A representation of an exported interface.

    The busRef indicates the name of the interface in the containing
    component.

    :ivar is_present:
    :ivar description:
    :ivar vendor_extensions:
    :ivar bus_ref: Reference to the components  bus interface
    :ivar id:
    """

    class Meta:
        name = "hierInterfaceType"

    is_present: None | IsPresent = field(
        default=None,
        metadata={
            "name": "isPresent",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    bus_ref: str = field(
        metadata={
            "name": "busRef",
            "type": "Attribute",
        }
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )


@dataclass(kw_only=True)
class IpxactFilesType:
    """
    Contains a list of IP-XACT files to include.
    """

    class Meta:
        name = "ipxactFilesType"

    ipxact_file: list[IpxactFileType] = field(
        default_factory=list,
        metadata={
            "name": "ipxactFile",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            "min_occurs": 1,
        },
    )


@dataclass(kw_only=True)
class MonitorInterconnection:
    """
    Describes a connection from the interface of one component to any
    number of monitor interfaces in the design.

    An active interface can be connected to unlimited number of monitor
    interfaces.

    :ivar name: Unique name
    :ivar display_name:
    :ivar description:
    :ivar is_present:
    :ivar monitored_active_interface: Describes an active interface of
        the design that all the monitors will be connected to. The
        componentRef and busRef attributes indicate the instance name
        and bus interface name. The optional path attribute indicates
        the hierarchical instance name path to the component.
    :ivar monitor_interface: Describes a list of monitor interfaces that
        are connected to the single active interface. The componentRef
        and busRef attributes indicate the instance name and bus
        interface name. The optional path attribute indicates the
        hierarchical instance name path to the component.
    """

    class Meta:
        name = "monitorInterconnection"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    name: str = field(
        metadata={
            "type": "Element",
        }
    )
    display_name: None | DisplayName = field(
        default=None,
        metadata={
            "name": "displayName",
            "type": "Element",
        },
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    is_present: None | IsPresent = field(
        default=None,
        metadata={
            "name": "isPresent",
            "type": "Element",
        },
    )
    monitored_active_interface: MonitorInterfaceType = field(
        metadata={
            "name": "monitoredActiveInterface",
            "type": "Element",
        }
    )
    monitor_interface: list[MonitorInterconnection.MonitorInterface] = field(
        default_factory=list,
        metadata={
            "name": "monitorInterface",
            "type": "Element",
            "min_occurs": 1,
        },
    )

    @dataclass(kw_only=True)
    class MonitorInterface(MonitorInterfaceType):
        is_present: None | IsPresent = field(
            default=None,
            metadata={
                "name": "isPresent",
                "type": "Element",
            },
        )


@dataclass(kw_only=True)
class NameValuePairType:
    """
    Name and value type for use in resolvable elements.

    :ivar name: Unique name
    :ivar display_name:
    :ivar description:
    :ivar value:
    :ivar vendor_extensions:
    :ivar id:
    """

    class Meta:
        name = "nameValuePairType"

    name: str = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    display_name: None | DisplayName = field(
        default=None,
        metadata={
            "name": "displayName",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    value: Value = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )


@dataclass(kw_only=True)
class OtherClockDriver(ClockDriverType):
    """
    Describes a clock not directly associated with an input port.

    The clockSource attribute can be used on these clocks to indicate the
    actual clock source (e.g. an output port of a clock generator cell).

    :ivar clock_name: Indicates the name of the clock.
    :ivar clock_source: Indicates the name of the actual clock source
        (e.g. an output pin of a clock generator cell).
    """

    class Meta:
        name = "otherClockDriver"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    clock_name: str = field(
        metadata={
            "name": "clockName",
            "type": "Attribute",
        }
    )
    clock_source: None | str = field(
        default=None,
        metadata={
            "name": "clockSource",
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class PathSegmentType:
    """
    Identifies one level of hierarchy in the view specifed by viewNameRef.

    This is a simple name and optionally some indices into a multi
    dimensional element.

    :ivar path_segment_name: One section of a HDL path
    :ivar indices: Specifies a multi-dimensional index into
        pathSegementName
    :ivar id:
    """

    class Meta:
        name = "pathSegmentType"

    path_segment_name: str = field(
        metadata={
            "name": "pathSegmentName",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    indices: None | IndicesType = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )


@dataclass(kw_only=True)
class Range:
    """
    Left and right bound of a reference into a vector.
    """

    class Meta:
        name = "range"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    left: Left = field(
        metadata={
            "type": "Element",
        }
    )
    right: Right = field(
        metadata={
            "type": "Element",
        }
    )


@dataclass(kw_only=True)
class TransparentBridge:
    """
    If this element is present, it indicates that the bus interface
    provides a transparent bridge to another master bus interface on the
    same component.

    It has a masterRef attribute which contains the name of the other bus
    interface. Any slave interface can bridge to multiple master
    interfaces, and multiple slave interfaces can bridge to the same master
    interface.

    :ivar is_present:
    :ivar master_ref: The name of the master bus interface to which this
        interface bridges.
    :ivar id:
    """

    class Meta:
        name = "transparentBridge"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    is_present: None | IsPresent = field(
        default=None,
        metadata={
            "name": "isPresent",
            "type": "Element",
        },
    )
    master_ref: str = field(
        metadata={
            "name": "masterRef",
            "type": "Attribute",
        }
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )


@dataclass(kw_only=True)
class Vector:
    """
    Left and right ranges of the vector.
    """

    class Meta:
        name = "vector"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    left: Left = field(
        metadata={
            "type": "Element",
        }
    )
    right: Right = field(
        metadata={
            "type": "Element",
        }
    )


@dataclass(kw_only=True)
class AddressSpaceRef(AddrSpaceRefType):
    """
    References the address space.

    The name of the address space is kept in its addressSpaceRef attribute.
    """

    class Meta:
        name = "addressSpaceRef"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"


@dataclass(kw_only=True)
class Arrays(ConfigurableArrays):
    class Meta:
        name = "arrays"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"


@dataclass(kw_only=True)
class Catalog:
    """
    :ivar vendor: Name of the vendor who supplies this file.
    :ivar library: Name of the logical library this element belongs to.
    :ivar name: The name of the object.
    :ivar version: Indicates the version of the named element.
    :ivar description:
    :ivar catalogs:
    :ivar bus_definitions:
    :ivar abstraction_definitions:
    :ivar components:
    :ivar abstractors:
    :ivar designs:
    :ivar design_configurations:
    :ivar generator_chains:
    :ivar vendor_extensions:
    """

    class Meta:
        name = "catalog"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    vendor: str = field(
        metadata={
            "type": "Element",
        }
    )
    library: str = field(
        metadata={
            "type": "Element",
        }
    )
    name: str = field(
        metadata={
            "type": "Element",
        }
    )
    version: str = field(
        metadata={
            "type": "Element",
        }
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    catalogs: None | IpxactFilesType = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    bus_definitions: None | IpxactFilesType = field(
        default=None,
        metadata={
            "name": "busDefinitions",
            "type": "Element",
        },
    )
    abstraction_definitions: None | IpxactFilesType = field(
        default=None,
        metadata={
            "name": "abstractionDefinitions",
            "type": "Element",
        },
    )
    components: None | IpxactFilesType = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    abstractors: None | IpxactFilesType = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    designs: None | IpxactFilesType = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    design_configurations: None | IpxactFilesType = field(
        default=None,
        metadata={
            "name": "designConfigurations",
            "type": "Element",
        },
    )
    generator_chains: None | IpxactFilesType = field(
        default=None,
        metadata={
            "name": "generatorChains",
            "type": "Element",
        },
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
        },
    )


@dataclass(kw_only=True)
class ComponentInstance:
    """
    Component instance element.

    The instance name is contained in the unique-value instanceName
    attribute.

    :ivar instance_name:
    :ivar display_name:
    :ivar description:
    :ivar is_present:
    :ivar component_ref: References a component to be found in an
        external library.  The four attributes define the VLNV of the
        referenced element.
    :ivar vendor_extensions:
    :ivar id:
    """

    class Meta:
        name = "componentInstance"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    instance_name: InstanceName = field(
        metadata={
            "name": "instanceName",
            "type": "Element",
        }
    )
    display_name: None | DisplayName = field(
        default=None,
        metadata={
            "name": "displayName",
            "type": "Element",
        },
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    is_present: None | IsPresent = field(
        default=None,
        metadata={
            "name": "isPresent",
            "type": "Element",
        },
    )
    component_ref: ConfigurableLibraryRefType = field(
        metadata={
            "name": "componentRef",
            "type": "Element",
        }
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )


@dataclass(kw_only=True)
class ConstraintSets:
    """
    List of constraintSet elements for a component port.
    """

    class Meta:
        name = "constraintSets"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    constraint_set: list[ConstraintSet] = field(
        default_factory=list,
        metadata={
            "name": "constraintSet",
            "type": "Element",
            "min_occurs": 1,
        },
    )


@dataclass(kw_only=True)
class DesignInstantiationType:
    """
    Design instantiation type.

    :ivar name: Unique name
    :ivar display_name:
    :ivar description:
    :ivar design_ref: References an IP-XACT design document (by VLNV)
        that provides a design for the component.
    :ivar vendor_extensions:
    :ivar id:
    """

    class Meta:
        name = "designInstantiationType"

    name: str = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    display_name: None | DisplayName = field(
        default=None,
        metadata={
            "name": "displayName",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    design_ref: ConfigurableLibraryRefType = field(
        metadata={
            "name": "designRef",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )


@dataclass(kw_only=True)
class DriverType:
    """
    Wire port driver type.
    """

    class Meta:
        name = "driverType"

    range: None | Range = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    default_value: None | DefaultValue = field(
        default=None,
        metadata={
            "name": "defaultValue",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    clock_driver: None | ClockDriver = field(
        default=None,
        metadata={
            "name": "clockDriver",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    single_shot_driver: None | SingleShotDriver = field(
        default=None,
        metadata={
            "name": "singleShotDriver",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )


@dataclass(kw_only=True)
class File:
    """
    IP-XACT reference to a file or directory.

    :ivar name: Path to the file or directory. If this path is a
        relative path, then it is relative to the containing XML file.
    :ivar is_present:
    :ivar file_type:
    :ivar is_structural: Indicates that the current file is purely
        structural.
    :ivar is_include_file: Indicate that the file is include file.
    :ivar logical_name: Logical name for this file or directory e.g.
        VHDL library name.
    :ivar exported_name: Defines exported names that can be accessed
        externally, e.g. exported function names from a C source file.
    :ivar build_command: Command and flags used to build derived files
        from the sourceName files. If this element is present, the
        command and/or flags used to to build the file will override or
        augment any default builders at a higher level.
    :ivar dependency:
    :ivar define: Specifies define symbols that are used in the source
        file.  The ipxact:name element gives the name to be defined and
        the text content of the ipxact:value element holds the value.
        This element supports full configurability.
    :ivar image_type: Relates the current file to a certain executable
        image type in the design.
    :ivar description: String for describing this file to users
    :ivar vendor_extensions:
    :ivar file_id: Unique ID for this file, referenced in
        fileSet/function/fileRef
    :ivar other_attributes:
    :ivar id:
    """

    class Meta:
        name = "file"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    name: StringUriexpression = field(
        metadata={
            "type": "Element",
        }
    )
    is_present: None | IsPresent = field(
        default=None,
        metadata={
            "name": "isPresent",
            "type": "Element",
        },
    )
    file_type: list[FileType] = field(
        default_factory=list,
        metadata={
            "name": "fileType",
            "type": "Element",
            "min_occurs": 1,
        },
    )
    is_structural: None | bool = field(
        default=None,
        metadata={
            "name": "isStructural",
            "type": "Element",
        },
    )
    is_include_file: None | File.IsIncludeFile = field(
        default=None,
        metadata={
            "name": "isIncludeFile",
            "type": "Element",
        },
    )
    logical_name: None | File.LogicalName = field(
        default=None,
        metadata={
            "name": "logicalName",
            "type": "Element",
        },
    )
    exported_name: list[File.ExportedName] = field(
        default_factory=list,
        metadata={
            "name": "exportedName",
            "type": "Element",
        },
    )
    build_command: None | File.BuildCommand = field(
        default=None,
        metadata={
            "name": "buildCommand",
            "type": "Element",
        },
    )
    dependency: list[Dependency] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    define: list[NameValuePairType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    image_type: list[File.ImageType] = field(
        default_factory=list,
        metadata={
            "name": "imageType",
            "type": "Element",
        },
    )
    description: None | str = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
        },
    )
    file_id: None | str = field(
        default=None,
        metadata={
            "name": "fileId",
            "type": "Attribute",
        },
    )
    other_attributes: dict[str, str] = field(
        default_factory=dict,
        metadata={
            "type": "Attributes",
            "namespace": "##other",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )

    @dataclass(kw_only=True)
    class IsIncludeFile:
        """
        :ivar value:
        :ivar external_declarations: the File contains some declarations
            that are needed in top file
        """

        value: bool = field()
        external_declarations: bool = field(
            default=False,
            metadata={
                "name": "externalDeclarations",
                "type": "Attribute",
            },
        )

    @dataclass(kw_only=True)
    class LogicalName:
        """
        :ivar value:
        :ivar default: The logical name shall only be used as a default
            and another process may override this name.
        """

        value: str = field(default="")
        default: bool = field(
            default=False,
            metadata={
                "type": "Attribute",
            },
        )

    @dataclass(kw_only=True)
    class ExportedName:
        value: str = field(default="")
        id: None | str = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.w3.org/XML/1998/namespace",
            },
        )

    @dataclass(kw_only=True)
    class BuildCommand:
        """
        :ivar command: Command used to build this file.
        :ivar flags: Flags given to the build command when building this
            file. If the optional attribute "append" is "true", this
            string will be appended to any existing flags, otherwise
            these flags will replace any existing default flags.
        :ivar replace_default_flags: If true, the value of the sibling
            element "flags" should replace any default flags specified
            at a more global level. If this is true and the sibling
            element "flags" is empty or missing, this has the effect of
            clearing any default flags.
        :ivar target_name: Pathname to the file that is derived (built)
            from the source file.
        """

        command: None | StringExpression = field(
            default=None,
            metadata={
                "type": "Element",
            },
        )
        flags: None | File.BuildCommand.Flags = field(
            default=None,
            metadata={
                "type": "Element",
            },
        )
        replace_default_flags: None | UnsignedBitExpression = field(
            default=None,
            metadata={
                "name": "replaceDefaultFlags",
                "type": "Element",
            },
        )
        target_name: None | StringUriexpression = field(
            default=None,
            metadata={
                "name": "targetName",
                "type": "Element",
            },
        )

        @dataclass(kw_only=True)
        class Flags(StringExpression):
            """
            :ivar append: "true" indicates that the flags shall be
                appended to any existing flags, "false"indicates these
                flags will replace any existing default flags.
            """

            append: None | bool = field(
                default=None,
                metadata={
                    "type": "Attribute",
                },
            )

    @dataclass(kw_only=True)
    class ImageType:
        value: str = field(default="")
        id: None | str = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.w3.org/XML/1998/namespace",
            },
        )


@dataclass(kw_only=True)
class IndexedAccessHandle:
    """
    :ivar view_ref: A list of views this accessHandle is applicable to.
        Note this element is optional, if it is not present the
        accessHandle applies to all views.
    :ivar indices: For a multi dimensional IP-XACT object, indices can
        be specified to select the element the accessHandle applies to.
        This is an index into a multi-dimensional array and follows
        C-semantics for indexing.
    :ivar path_segments: An ordered list of pathSegment elements. When
        concatenated with a desired separator the elements in this form
        a HDL path for the parent slice into the referenced view.
    :ivar id:
    """

    class Meta:
        name = "indexedAccessHandle"

    view_ref: list[IndexedAccessHandle.ViewRef] = field(
        default_factory=list,
        metadata={
            "name": "viewRef",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    indices: None | IndexedAccessHandle.Indices = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    path_segments: IndexedAccessHandle.PathSegments = field(
        metadata={
            "name": "pathSegments",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )

    @dataclass(kw_only=True)
    class ViewRef:
        value: str = field(default="")
        id: None | str = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.w3.org/XML/1998/namespace",
            },
        )

    @dataclass(kw_only=True)
    class Indices:
        """
        :ivar index: An index into the IP-XACT object.
        """

        index: list[UnsignedIntExpression] = field(
            default_factory=list,
            metadata={
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                "min_occurs": 1,
            },
        )

    @dataclass(kw_only=True)
    class PathSegments:
        path_segment: list[PathSegmentType] = field(
            default_factory=list,
            metadata={
                "name": "pathSegment",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                "min_occurs": 1,
            },
        )


@dataclass(kw_only=True)
class Interconnection:
    """
    Describes a connection between two active (not monitor) busInterfaces.

    :ivar name: Unique name
    :ivar display_name:
    :ivar description:
    :ivar is_present:
    :ivar active_interface: Describes one interface of the
        interconnection. The componentRef and busRef attributes indicate
        the instance name and bus interface name of one end of the
        connection.
        This interface can be connected to one or more additional active
        and/or hierarchical interfaces, or to one or more hierarchical
        interfaces or to one or more monitor interfaces. The connected
        interfaces are all contained within the choice element below.
    :ivar hier_interface:
    :ivar vendor_extensions:
    :ivar id:
    """

    class Meta:
        name = "interconnection"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    name: str = field(
        metadata={
            "type": "Element",
        }
    )
    display_name: None | DisplayName = field(
        default=None,
        metadata={
            "name": "displayName",
            "type": "Element",
        },
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    is_present: None | IsPresent = field(
        default=None,
        metadata={
            "name": "isPresent",
            "type": "Element",
        },
    )
    active_interface: list[ActiveInterface] = field(
        default_factory=list,
        metadata={
            "name": "activeInterface",
            "type": "Element",
            "min_occurs": 1,
            "sequence": 1,
        },
    )
    hier_interface: list[HierInterfaceType] = field(
        default_factory=list,
        metadata={
            "name": "hierInterface",
            "type": "Element",
        },
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )


@dataclass(kw_only=True)
class OtherClocks:
    """
    List of clocks associated with the component that are not associated
    with ports.

    Set the clockSource attribute on the clockDriver to indicate the source
    of a clock not associated with a particular component port.
    """

    class Meta:
        name = "otherClocks"

    other_clock_driver: list[OtherClockDriver] = field(
        default_factory=list,
        metadata={
            "name": "otherClockDriver",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            "min_occurs": 1,
        },
    )


@dataclass(kw_only=True)
class PartSelect:
    """
    Bit range definition.
    """

    class Meta:
        name = "partSelect"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    range: None | Range = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    indices: None | IndicesType = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )


@dataclass(kw_only=True)
class SimpleAccessHandle:
    """
    :ivar view_ref: A list of views this accessHandle is applicable to.
        Note this element is optional, if it is not present the
        accessHandle applies to all views.
    :ivar path_segments: An ordered list of pathSegment elements. When
        concatenated with a desired separator the elements in this form
        a HDL path for the parent slice into the referenced view.
    :ivar id:
    """

    class Meta:
        name = "simpleAccessHandle"

    view_ref: list[SimpleAccessHandle.ViewRef] = field(
        default_factory=list,
        metadata={
            "name": "viewRef",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    path_segments: SimpleAccessHandle.PathSegments = field(
        metadata={
            "name": "pathSegments",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )

    @dataclass(kw_only=True)
    class ViewRef:
        value: str = field(default="")
        id: None | str = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.w3.org/XML/1998/namespace",
            },
        )

    @dataclass(kw_only=True)
    class PathSegments:
        path_segment: list[PathSegmentType] = field(
            default_factory=list,
            metadata={
                "name": "pathSegment",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                "min_occurs": 1,
            },
        )


@dataclass(kw_only=True)
class SliceType:
    """
    Contains the HDL path information for a slice of the IP-XACT object.

    :ivar path_segments: An ordered list of pathSegment elements. When
        concatenated with a desired separator the elements in this form
        a HDL path for the parent slice into the referenced view.
    :ivar range: A range to be applied to the concatenation of the above
        path segments
    :ivar id:
    """

    class Meta:
        name = "sliceType"

    path_segments: SliceType.PathSegments = field(
        metadata={
            "name": "pathSegments",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    range: None | Range = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )

    @dataclass(kw_only=True)
    class PathSegments:
        path_segment: list[PathSegmentType] = field(
            default_factory=list,
            metadata={
                "name": "pathSegment",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                "min_occurs": 1,
            },
        )


@dataclass(kw_only=True)
class Vectors:
    """
    Vectored information.
    """

    class Meta:
        name = "vectors"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    vector: list[Vector] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "min_occurs": 1,
        },
    )


@dataclass(kw_only=True)
class AbstractionTypes:
    """
    :ivar abstraction_type: The abstraction type/level of this
        interface. Refers to abstraction definition using vendor,
        library, name, version attributes along with any configurable
        element values needed to configure this abstraction. Bus
        definition can be found through a reference in this file.
    """

    class Meta:
        name = "abstractionTypes"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    abstraction_type: list[AbstractionTypes.AbstractionType] = field(
        default_factory=list,
        metadata={
            "name": "abstractionType",
            "type": "Element",
            "min_occurs": 1,
        },
    )

    @dataclass(kw_only=True)
    class AbstractionType:
        """
        :ivar view_ref: A reference to a view name in the file for which
            this type applies.
        :ivar abstraction_ref: Provides the VLNV of the abstraction
            type.
        :ivar port_maps: Listing of maps between component ports and bus
            ports.
        :ivar id:
        """

        view_ref: list[ViewRef] = field(
            default_factory=list,
            metadata={
                "name": "viewRef",
                "type": "Element",
            },
        )
        abstraction_ref: ConfigurableLibraryRefType = field(
            metadata={
                "name": "abstractionRef",
                "type": "Element",
            }
        )
        port_maps: None | AbstractionTypes.AbstractionType.PortMaps = field(
            default=None,
            metadata={
                "name": "portMaps",
                "type": "Element",
            },
        )
        id: None | str = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.w3.org/XML/1998/namespace",
            },
        )

        @dataclass(kw_only=True)
        class PortMaps:
            """
            :ivar port_map: Maps a component's port to a port in a bus
                description. This is the logical to physical mapping.
                The logical pin comes from the bus interface and the
                physical pin from the component.
            """

            port_map: list[
                AbstractionTypes.AbstractionType.PortMaps.PortMap
            ] = field(
                default_factory=list,
                metadata={
                    "name": "portMap",
                    "type": "Element",
                    "min_occurs": 1,
                },
            )

            @dataclass(kw_only=True)
            class PortMap:
                """
                :ivar is_present:
                :ivar logical_port: Logical port from abstraction
                    definition
                :ivar physical_port: Physical port from this component
                :ivar logical_tie_off: Identifies a value to tie this
                    logical port to.
                :ivar is_informative: When true, indicates that this
                    portMap element is for information purpose only.
                :ivar id:
                :ivar invert: Indicates that the connection between the
                    logical and physical ports should include an
                    inversion.
                """

                is_present: None | IsPresent = field(
                    default=None,
                    metadata={
                        "name": "isPresent",
                        "type": "Element",
                    },
                )
                logical_port: AbstractionTypes.AbstractionType.PortMaps.PortMap.LogicalPort = field(
                    metadata={
                        "name": "logicalPort",
                        "type": "Element",
                    }
                )
                physical_port: (
                    None
                    | AbstractionTypes.AbstractionType.PortMaps.PortMap.PhysicalPort
                ) = field(
                    default=None,
                    metadata={
                        "name": "physicalPort",
                        "type": "Element",
                    },
                )
                logical_tie_off: None | UnsignedPositiveIntExpression = field(
                    default=None,
                    metadata={
                        "name": "logicalTieOff",
                        "type": "Element",
                    },
                )
                is_informative: None | bool = field(
                    default=None,
                    metadata={
                        "name": "isInformative",
                        "type": "Element",
                    },
                )
                id: None | str = field(
                    default=None,
                    metadata={
                        "type": "Attribute",
                        "namespace": "http://www.w3.org/XML/1998/namespace",
                    },
                )
                invert: object = field(
                    default="false",
                    metadata={
                        "type": "Attribute",
                    },
                )

                @dataclass(kw_only=True)
                class LogicalPort:
                    """
                    :ivar name: Bus port name as specified inside the
                        abstraction definition
                    :ivar range:
                    """

                    name: str = field(
                        metadata={
                            "type": "Element",
                        }
                    )
                    range: None | Range = field(
                        default=None,
                        metadata={
                            "type": "Element",
                        },
                    )

                @dataclass(kw_only=True)
                class PhysicalPort:
                    """
                    :ivar name: Component port name as specified inside
                        the model port section
                    :ivar part_select:
                    """

                    name: str = field(
                        metadata={
                            "type": "Element",
                            "white_space": "collapse",
                            "pattern": r"\i[\p{L}\p{N}\.\-:_]*",
                        }
                    )
                    part_select: None | PartSelect = field(
                        default=None,
                        metadata={
                            "name": "partSelect",
                            "type": "Element",
                        },
                    )


@dataclass(kw_only=True)
class ComponentInstances:
    """
    Sub instances of internal components.
    """

    class Meta:
        name = "componentInstances"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    component_instance: list[ComponentInstance] = field(
        default_factory=list,
        metadata={
            "name": "componentInstance",
            "type": "Element",
            "min_occurs": 1,
        },
    )


@dataclass(kw_only=True)
class Driver(DriverType):
    """
    Wire port driver element.
    """

    class Meta:
        name = "driver"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"


@dataclass(kw_only=True)
class ExternalPortReference:
    """
    :ivar is_present:
    :ivar part_select:
    :ivar port_ref: A port on the on the referenced component from
        componentRef.
    :ivar id:
    """

    class Meta:
        name = "externalPortReference"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    is_present: None | IsPresent = field(
        default=None,
        metadata={
            "name": "isPresent",
            "type": "Element",
        },
    )
    part_select: None | PartSelect = field(
        default=None,
        metadata={
            "name": "partSelect",
            "type": "Element",
        },
    )
    port_ref: str = field(
        metadata={
            "name": "portRef",
            "type": "Attribute",
            "white_space": "collapse",
            "pattern": r"\i[\p{L}\p{N}\.\-:_]*",
        }
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )


@dataclass(kw_only=True)
class FileSetType:
    """
    :ivar name: Unique name
    :ivar display_name:
    :ivar description:
    :ivar group: Identifies this filleSet as belonging to a particular
        group or having a particular purpose. Examples might be
        "diagnostics", "boot", "application", "interrupt",
        "deviceDriver", etc.
    :ivar file:
    :ivar default_file_builder: Default command and flags used to build
        derived files from the sourceName files in this file set.
    :ivar dependency:
    :ivar function: Generator information if this file set describes a
        function. For example, this file set may describe diagnostics
        for which the DE can generate a diagnostics driver.
    :ivar vendor_extensions:
    :ivar id:
    """

    class Meta:
        name = "fileSetType"

    name: str = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    display_name: None | DisplayName = field(
        default=None,
        metadata={
            "name": "displayName",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    group: list[FileSetType.Group] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    file: list[File] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    default_file_builder: list[FileBuilderType] = field(
        default_factory=list,
        metadata={
            "name": "defaultFileBuilder",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    dependency: list[Dependency] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    function: list[FileSetType.Function] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )

    @dataclass(kw_only=True)
    class Group:
        value: str = field(default="")
        id: None | str = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.w3.org/XML/1998/namespace",
            },
        )

    @dataclass(kw_only=True)
    class Function:
        """
        :ivar entry_point: Optional name for the function.
        :ivar file_ref: A reference to the file that contains the entry
            point function.
        :ivar return_type: Function return type. Possible values are
            void and int.
        :ivar argument: Arguments passed in when the function is called.
            Arguments are passed in order. This is an extension of the
            name-value pair which includes the data type in the
            ipxact:dataType attribute.  The argument name is in the
            ipxact:name element and its value is in the ipxact:value
            element.
        :ivar disabled: Specifies if the SW function is enabled. If not
            present the function is always enabled.
        :ivar source_file: Location information for the source file of
            this function.
        :ivar replicate: If true directs the generator to compile a
            separate object module for each instance of the component in
            the design. If false (default) the function will be called
            with different arguments for each instance.
        :ivar id:
        """

        entry_point: None | str = field(
            default=None,
            metadata={
                "name": "entryPoint",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            },
        )
        file_ref: str = field(
            metadata={
                "name": "fileRef",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            }
        )
        return_type: None | ReturnTypeType = field(
            default=None,
            metadata={
                "name": "returnType",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            },
        )
        argument: list[FileSetType.Function.Argument] = field(
            default_factory=list,
            metadata={
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            },
        )
        disabled: None | UnsignedBitExpression = field(
            default=None,
            metadata={
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            },
        )
        source_file: list[FileSetType.Function.SourceFile] = field(
            default_factory=list,
            metadata={
                "name": "sourceFile",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            },
        )
        replicate: bool = field(
            default=False,
            metadata={
                "type": "Attribute",
            },
        )
        id: None | str = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.w3.org/XML/1998/namespace",
            },
        )

        @dataclass(kw_only=True)
        class Argument(NameValuePairType):
            """
            :ivar data_type: The data type of the argument as pertains
                to the language. Example: "int", "double", "char *".
            """

            data_type: DataTypeType = field(
                metadata={
                    "name": "dataType",
                    "type": "Attribute",
                }
            )

        @dataclass(kw_only=True)
        class SourceFile:
            """
            :ivar source_name: Source file for the boot load.  Relative
                names are searched for in the project directory and the
                source of the component directory.
            :ivar file_type:
            :ivar id:
            """

            source_name: IpxactUri = field(
                metadata={
                    "name": "sourceName",
                    "type": "Element",
                    "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                }
            )
            file_type: FileType = field(
                metadata={
                    "name": "fileType",
                    "type": "Element",
                    "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                }
            )
            id: None | str = field(
                default=None,
                metadata={
                    "type": "Attribute",
                    "namespace": "http://www.w3.org/XML/1998/namespace",
                },
            )


@dataclass(kw_only=True)
class Interconnections:
    """
    Connections between internal sub components.
    """

    class Meta:
        name = "interconnections"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    interconnection: list[Interconnection] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    monitor_interconnection: list[MonitorInterconnection] = field(
        default_factory=list,
        metadata={
            "name": "monitorInterconnection",
            "type": "Element",
        },
    )


@dataclass(kw_only=True)
class ParameterBaseType:
    """
    Name and value type for use in resolvable elements.

    :ivar name: Unique name
    :ivar display_name:
    :ivar description:
    :ivar vectors:
    :ivar arrays:
    :ivar value: The value of the parameter.
    :ivar vendor_extensions:
    :ivar parameter_id: ID attribute for uniquely identifying a
        parameter within its document. Attribute is used to refer to
        this from a configurable element.
    :ivar prompt: Provides a string used to prompt the user for user-
        resolved property values.
    :ivar choice_ref: For user defined properties, refers the choice
        element enumerating the values to choose from.
    :ivar order: For components with auto-generated configuration forms,
        the user-resolved properties with order attibutes will be
        presented in ascending order.
    :ivar config_groups: Tags configurable properties so that they may
        be grouped together.  Configurable properties with matching
        values for this attribute are contained in the same group. The
        format of this attribute is a string. There is no semantic
        meaning to this attribute.
    :ivar minimum: For user-resolved properties with numeric values,
        this indicates the minimum value allowed. Only valid for the
        types: byte, shortint, int, longint, shortreal and real. The
        type of this value is the same as the type of the parameter-
        value, which is specified by the parameter-type attribute.
    :ivar maximum: For user-resolved properties with numeric values,
        this indicates the maximum value allowed. Only valid for the
        types: byte, shortint, int, longint, shortreal and real. The
        type of this value is the same as the type of the parameter-
        value, which is specified by the parameter-type attribute.
    :ivar type_value: Specifies the type of the value of the parameter.
        A parameter of type byte is resolved to an 8-bit integer value,
        shortint is resolved to a 16-bit integer value, int is resolved
        to a 32-bit integer value, longint is resolved to a 64-bit
        integer value, shortreal is resolved to a 32-bit floating point
        value, real is resolved to a 64-bit floating point value, bit is
        by default resolved to a one bit value, unless a vector size has
        been specified and the string type is resolved to a string
        value.
    :ivar sign: Specify the signedness explicitly. The data types byte,
        shortint, int, longint default to signed. The data type bit
        defaults to unsigned. When setting this values for the data
        types string, real and shortreal the setting is ignored.
    :ivar prefix: Defines the prefix that precedes the unit of a value.
        The prefix is not applied to the value (e.g. in calculations).
    :ivar unit: Defines the unit of the value.
    :ivar other_attributes:
    """

    class Meta:
        name = "parameterBaseType"

    name: str = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    display_name: None | DisplayName = field(
        default=None,
        metadata={
            "name": "displayName",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    vectors: None | Vectors = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    arrays: None | ConfigurableArrays = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    value: ComplexBaseExpression = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    parameter_id: None | str = field(
        default=None,
        metadata={
            "name": "parameterId",
            "type": "Attribute",
        },
    )
    prompt: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    choice_ref: None | str = field(
        default=None,
        metadata={
            "name": "choiceRef",
            "type": "Attribute",
        },
    )
    order: None | float = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    config_groups: list[str] = field(
        default_factory=list,
        metadata={
            "name": "configGroups",
            "type": "Attribute",
            "tokens": True,
        },
    )
    minimum: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    maximum: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    type_value: FormatType = field(
        default=FormatType.STRING,
        metadata={
            "name": "type",
            "type": "Attribute",
        },
    )
    sign: None | SignType = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    prefix: None | ParameterBaseTypePrefix = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    unit: None | ParameterBaseTypeUnit = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    other_attributes: dict[str, str] = field(
        default_factory=dict,
        metadata={
            "type": "Attributes",
            "namespace": "##other",
        },
    )


@dataclass(kw_only=True)
class SlicesType:
    """
    Each slice specifies the HDL path for part of the parent IP-XACT
    object.

    The slices must be concatenated to calculate the entire path. If there
    is only one slice, it is assumed to be the path for the entire IP-XACT
    object.

    :ivar slice: The HDL path for a slice of the IP-XACT object.
    """

    class Meta:
        name = "slicesType"

    slice: list[SliceType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            "min_occurs": 1,
        },
    )


@dataclass(kw_only=True)
class AdHocConnection:
    """
    Represents an ad-hoc connection between component ports.

    :ivar name: Unique name
    :ivar display_name:
    :ivar description:
    :ivar is_present:
    :ivar tied_value: The logic value of this connection. The value can
        be an unsigned longint expression or open or default. Only valid
        for ports of style wire.
    :ivar port_references: Liist of internal and external port
        references involved in the adhocConnection
    :ivar vendor_extensions:
    :ivar id:
    """

    class Meta:
        name = "adHocConnection"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    name: str = field(
        metadata={
            "type": "Element",
            "white_space": "collapse",
            "pattern": r"\i[\p{L}\p{N}\.\-:_]*",
        }
    )
    display_name: None | DisplayName = field(
        default=None,
        metadata={
            "name": "displayName",
            "type": "Element",
        },
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    is_present: None | IsPresent = field(
        default=None,
        metadata={
            "name": "isPresent",
            "type": "Element",
        },
    )
    tied_value: None | ComplexTiedValueType = field(
        default=None,
        metadata={
            "name": "tiedValue",
            "type": "Element",
        },
    )
    port_references: AdHocConnection.PortReferences = field(
        metadata={
            "name": "portReferences",
            "type": "Element",
        }
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )

    @dataclass(kw_only=True)
    class PortReferences:
        """
        :ivar internal_port_reference: Defines a reference to a port on
            a component contained within the design.
        :ivar external_port_reference:
        """

        internal_port_reference: list[
            AdHocConnection.PortReferences.InternalPortReference
        ] = field(
            default_factory=list,
            metadata={
                "name": "internalPortReference",
                "type": "Element",
            },
        )
        external_port_reference: list[ExternalPortReference] = field(
            default_factory=list,
            metadata={
                "name": "externalPortReference",
                "type": "Element",
            },
        )

        @dataclass(kw_only=True)
        class InternalPortReference:
            """
            :ivar is_present:
            :ivar part_select:
            :ivar component_ref: A reference to the instanceName element
                of a component in this design.
            :ivar port_ref: A port on the on the referenced component
                from componentRef.
            :ivar id:
            """

            is_present: None | IsPresent = field(
                default=None,
                metadata={
                    "name": "isPresent",
                    "type": "Element",
                },
            )
            part_select: None | PartSelect = field(
                default=None,
                metadata={
                    "name": "partSelect",
                    "type": "Element",
                },
            )
            component_ref: str = field(
                metadata={
                    "name": "componentRef",
                    "type": "Attribute",
                }
            )
            port_ref: str = field(
                metadata={
                    "name": "portRef",
                    "type": "Attribute",
                    "white_space": "collapse",
                    "pattern": r"\i[\p{L}\p{N}\.\-:_]*",
                }
            )
            id: None | str = field(
                default=None,
                metadata={
                    "type": "Attribute",
                    "namespace": "http://www.w3.org/XML/1998/namespace",
                },
            )


@dataclass(kw_only=True)
class Drivers:
    """
    Container for wire port driver elements.

    :ivar driver: Wire port driver element. If no range is specified,
        default value applies to the entire range.
    """

    class Meta:
        name = "drivers"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    driver: list[Driver] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "min_occurs": 1,
        },
    )


@dataclass(kw_only=True)
class FileSet(FileSetType):
    """
    This element specifies a list of unique pathnames to files and
    directories.

    It may also include build instructions for the files. If compilation
    order is important, e.g. for VHDL files, the files have to be provided
    in compilation order.
    """

    class Meta:
        name = "fileSet"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"


@dataclass(kw_only=True)
class LeafAccessHandle:
    """
    :ivar view_ref: A list of views this accessHandle is applicable to.
        Note this element is optional, if it is not present the
        accessHandle applies to all views.
    :ivar indices: For a multi dimensional IP-XACT object, indices can
        be specified to select the element the accessHandle applies to.
        This is an index into a multi-dimensional array and follows
        C-semantics for indexing.
    :ivar slices:
    :ivar force:
    :ivar id:
    """

    class Meta:
        name = "leafAccessHandle"

    view_ref: list[LeafAccessHandle.ViewRef] = field(
        default_factory=list,
        metadata={
            "name": "viewRef",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    indices: None | LeafAccessHandle.Indices = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    slices: SlicesType = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    force: bool = field(
        default=True,
        metadata={
            "type": "Attribute",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )

    @dataclass(kw_only=True)
    class ViewRef:
        value: str = field(default="")
        id: None | str = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.w3.org/XML/1998/namespace",
            },
        )

    @dataclass(kw_only=True)
    class Indices:
        """
        :ivar index: An index into the IP-XACT object.
        """

        index: list[UnsignedIntExpression] = field(
            default_factory=list,
            metadata={
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                "min_occurs": 1,
            },
        )


@dataclass(kw_only=True)
class NonIndexedLeafAccessHandle:
    """
    :ivar view_ref: A list of views this accessHandle is applicable to.
        Note this element is optional, if it is not present the
        accessHandle applies to all views.
    :ivar slices:
    :ivar force:
    :ivar id:
    """

    class Meta:
        name = "nonIndexedLeafAccessHandle"

    view_ref: list[NonIndexedLeafAccessHandle.ViewRef] = field(
        default_factory=list,
        metadata={
            "name": "viewRef",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    slices: SlicesType = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    force: bool = field(
        default=True,
        metadata={
            "type": "Attribute",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )

    @dataclass(kw_only=True)
    class ViewRef:
        value: str = field(default="")
        id: None | str = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.w3.org/XML/1998/namespace",
            },
        )


@dataclass(kw_only=True)
class ParameterType(ParameterBaseType):
    """
    :ivar resolve: Determines how a property value can be configured.
    """

    class Meta:
        name = "parameterType"

    resolve: ParameterTypeResolve = field(
        default=ParameterTypeResolve.IMMEDIATE,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class WhiteboxElementRefType:
    """
    Reference to a whiteboxElement within a view.

    The 'name' attribute must refer to a whiteboxElement defined within
    this component.

    :ivar is_present:
    :ivar location: The contents of each location element can be used to
        specified one location (HDL Path) through the referenced
        whiteBoxElement is accessible.
    :ivar name: Reference to a whiteboxElement defined within this
        component.
    :ivar id:
    """

    class Meta:
        name = "whiteboxElementRefType"

    is_present: None | IsPresent = field(
        default=None,
        metadata={
            "name": "isPresent",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    location: list[SlicesType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            "min_occurs": 1,
        },
    )
    name: str = field(
        metadata={
            "type": "Attribute",
        }
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )


@dataclass(kw_only=True)
class AdHocConnections:
    """
    Defines the set of ad-hoc connections in a design.

    An ad-hoc connection represents a connection between two component pins
    which were not connected as a result of interface connections (i.e.the
    pin to pin connection was made explicitly and is represented
    explicitly).
    """

    class Meta:
        name = "adHocConnections"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    ad_hoc_connection: list[AdHocConnection] = field(
        default_factory=list,
        metadata={
            "name": "adHocConnection",
            "type": "Element",
            "min_occurs": 1,
        },
    )


@dataclass(kw_only=True)
class FileSets:
    """
    List of file sets associated with component.
    """

    class Meta:
        name = "fileSets"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    file_set: list[FileSet] = field(
        default_factory=list,
        metadata={
            "name": "fileSet",
            "type": "Element",
            "min_occurs": 1,
        },
    )


@dataclass(kw_only=True)
class ModuleParameterType(ParameterType):
    """
    Name value pair with data type information.

    :ivar is_present:
    :ivar data_type: The data type of the argument as pertains to the
        language. Example: "int", "double", "char *".
    :ivar usage_type: Indicates the type of the module parameter. Legal
        values are defined in the attribute enumeration list. Default
        value is 'nontyped'.
    """

    class Meta:
        name = "moduleParameterType"

    is_present: None | IsPresent = field(
        default=None,
        metadata={
            "name": "isPresent",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    data_type: None | str = field(
        default=None,
        metadata={
            "name": "dataType",
            "type": "Attribute",
        },
    )
    usage_type: ModuleParameterTypeUsageType = field(
        default=ModuleParameterTypeUsageType.NONTYPED,
        metadata={
            "name": "usageType",
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class Parameter(ParameterType):
    """
    A name value pair.

    The name is specified by the name element. The value is in the text
    content of the value element. This value element supports all
    configurability attributes.
    """

    class Meta:
        name = "parameter"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"


@dataclass(kw_only=True)
class PortAccessType1:
    """
    :ivar port_access_type: Indicates how a netlister accesses a port.
        'ref' means accessed by reference (default) and 'ptr' means
        accessed through a pointer.
    :ivar access_handles:
    """

    class Meta:
        name = "portAccessType"

    port_access_type: None | PortAccessType = field(
        default=None,
        metadata={
            "name": "portAccessType",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    access_handles: None | PortAccessType1.AccessHandles = field(
        default=None,
        metadata={
            "name": "accessHandles",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )

    @dataclass(kw_only=True)
    class AccessHandles:
        access_handle: list[LeafAccessHandle] = field(
            default_factory=list,
            metadata={
                "name": "accessHandle",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                "min_occurs": 1,
            },
        )


@dataclass(kw_only=True)
class PortWireType:
    """
    Wire port type for a component.

    :ivar direction: The direction of a wire style port. The basic
        directions for a port are 'in' for input ports, 'out' for output
        port and 'inout' for bidirectional and tristate ports. A value
        of 'phantom' is also allowed and define a port that exist on the
        IP-XACT component but not on the HDL model.
    :ivar vectors:
    :ivar wire_type_defs:
    :ivar drivers:
    :ivar constraint_sets:
    :ivar all_logical_directions_allowed: True if logical ports with
        different directions from the physical port direction may be
        mapped onto this port. Forbidden for phantom ports, which always
        allow logical ports with all direction value to be mapped onto
        the physical port. Also ignored for inout ports, since any
        logical port maybe mapped to a physical inout port.
    """

    class Meta:
        name = "portWireType"

    direction: ComponentPortDirectionType = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    vectors: None | Vectors = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    wire_type_defs: None | WireTypeDefs = field(
        default=None,
        metadata={
            "name": "wireTypeDefs",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    drivers: None | Drivers = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    constraint_sets: None | ConstraintSets = field(
        default=None,
        metadata={
            "name": "constraintSets",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    all_logical_directions_allowed: bool = field(
        default=False,
        metadata={
            "name": "allLogicalDirectionsAllowed",
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class AbstractorPortWireType(PortWireType):
    """
    Wire port type for an abstractor.
    """

    class Meta:
        name = "abstractorPortWireType"

    constraint_sets: Any = field(
        init=False,
        default=None,
        metadata={
            "type": "Ignore",
        },
    )


@dataclass(kw_only=True)
class Parameters:
    """
    A collection of parameters and associated value assertions.
    """

    class Meta:
        name = "parameters"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    parameter: list[Parameter] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "min_occurs": 1,
        },
    )


@dataclass(kw_only=True)
class TypeParameter(ModuleParameterType):
    """
    A typed parameter name value pair.

    The optional attribute dataType defines the type of the value and the
    usageType attribute indicates how the parameter is to be used.
    """

    class Meta:
        name = "typeParameter"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"


@dataclass(kw_only=True)
class AbstractionDefinition:
    """
    Define the ports and other information of a particular abstraction of
    the bus.

    :ivar vendor: Name of the vendor who supplies this file.
    :ivar library: Name of the logical library this element belongs to.
    :ivar name: The name of the object.
    :ivar version: Indicates the version of the named element.
    :ivar bus_type: Reference to the busDefinition that this
        abstractionDefinition implements.
    :ivar extends: Optional name of abstraction type that this
        abstraction definition is compatible with. This abstraction
        definition may change the definitions of ports in the existing
        abstraction definition and add new ports, the ports in the
        original abstraction are not deleted but may be marked illegal
        to disallow their use. This abstraction definition may only
        extend another abstraction definition if the bus type of this
        abstraction definition extends the bus type of the extended
        abstraction definition
    :ivar ports: This is a list of logical ports defined by the bus.
    :ivar description:
    :ivar parameters:
    :ivar assertions:
    :ivar vendor_extensions:
    :ivar id:
    """

    class Meta:
        name = "abstractionDefinition"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    vendor: str = field(
        metadata={
            "type": "Element",
        }
    )
    library: str = field(
        metadata={
            "type": "Element",
        }
    )
    name: str = field(
        metadata={
            "type": "Element",
        }
    )
    version: str = field(
        metadata={
            "type": "Element",
        }
    )
    bus_type: LibraryRefType = field(
        metadata={
            "name": "busType",
            "type": "Element",
        }
    )
    extends: None | LibraryRefType = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    ports: AbstractionDefinition.Ports = field(
        metadata={
            "type": "Element",
        }
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    parameters: None | Parameters = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    assertions: None | Assertions = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )

    @dataclass(kw_only=True)
    class Ports:
        port: list[AbstractionDefinition.Ports.Port] = field(
            default_factory=list,
            metadata={
                "type": "Element",
                "min_occurs": 1,
            },
        )

        @dataclass(kw_only=True)
        class Port:
            """
            :ivar is_present:
            :ivar logical_name: The assigned name of this port in bus
                specifications.
            :ivar display_name:
            :ivar description:
            :ivar wire: A port that carries logic or an array of logic
                values
            :ivar transactional: A port that carries complex information
                modeled at a high level of abstraction.
            :ivar vendor_extensions:
            :ivar id:
            """

            is_present: None | IsPresent = field(
                default=None,
                metadata={
                    "name": "isPresent",
                    "type": "Element",
                },
            )
            logical_name: str = field(
                metadata={
                    "name": "logicalName",
                    "type": "Element",
                }
            )
            display_name: None | DisplayName = field(
                default=None,
                metadata={
                    "name": "displayName",
                    "type": "Element",
                },
            )
            description: None | Description = field(
                default=None,
                metadata={
                    "type": "Element",
                },
            )
            wire: None | AbstractionDefinition.Ports.Port.Wire = field(
                default=None,
                metadata={
                    "type": "Element",
                },
            )
            transactional: (
                None | AbstractionDefinition.Ports.Port.Transactional
            ) = field(
                default=None,
                metadata={
                    "type": "Element",
                },
            )
            vendor_extensions: None | VendorExtensions = field(
                default=None,
                metadata={
                    "name": "vendorExtensions",
                    "type": "Element",
                },
            )
            id: None | str = field(
                default=None,
                metadata={
                    "type": "Attribute",
                    "namespace": "http://www.w3.org/XML/1998/namespace",
                },
            )

            @dataclass(kw_only=True)
            class Wire:
                """
                :ivar qualifier: The type of information this port
                    carries A wire port can carry both address and data,
                    but may not mix this with a clock or reset
                :ivar on_system: Defines constraints for this port when
                    present in a system bus interface with a matching
                    group name.
                :ivar on_master: Defines constraints for this port when
                    present in a master bus interface.
                :ivar on_slave: Defines constraints for this port when
                    present in a slave bus interface.
                :ivar default_value: Indicates the default value for
                    this wire port.
                :ivar requires_driver:
                """

                qualifier: (
                    None | AbstractionDefinition.Ports.Port.Wire.Qualifier
                ) = field(
                    default=None,
                    metadata={
                        "type": "Element",
                    },
                )
                on_system: list[
                    AbstractionDefinition.Ports.Port.Wire.OnSystem
                ] = field(
                    default_factory=list,
                    metadata={
                        "name": "onSystem",
                        "type": "Element",
                    },
                )
                on_master: (
                    None | AbstractionDefinition.Ports.Port.Wire.OnMaster
                ) = field(
                    default=None,
                    metadata={
                        "name": "onMaster",
                        "type": "Element",
                    },
                )
                on_slave: (
                    None | AbstractionDefinition.Ports.Port.Wire.OnSlave
                ) = field(
                    default=None,
                    metadata={
                        "name": "onSlave",
                        "type": "Element",
                    },
                )
                default_value: None | UnsignedBitVectorExpression = field(
                    default=None,
                    metadata={
                        "name": "defaultValue",
                        "type": "Element",
                    },
                )
                requires_driver: None | RequiresDriver = field(
                    default=None,
                    metadata={
                        "name": "requiresDriver",
                        "type": "Element",
                    },
                )

                @dataclass(kw_only=True)
                class Qualifier:
                    """
                    :ivar is_address: If this element is present, the
                        port contains address information.
                    :ivar is_data: If this element is present, the port
                        contains data information.
                    :ivar is_clock: If this element is present, the port
                        contains only clock information.
                    :ivar is_reset: Is this element is present, the port
                        contains only reset information.
                    """

                    is_address: None | bool = field(
                        default=None,
                        metadata={
                            "name": "isAddress",
                            "type": "Element",
                        },
                    )
                    is_data: None | bool = field(
                        default=None,
                        metadata={
                            "name": "isData",
                            "type": "Element",
                        },
                    )
                    is_clock: None | bool = field(
                        default=None,
                        metadata={
                            "name": "isClock",
                            "type": "Element",
                        },
                    )
                    is_reset: None | bool = field(
                        default=None,
                        metadata={
                            "name": "isReset",
                            "type": "Element",
                        },
                    )

                @dataclass(kw_only=True)
                class OnSystem:
                    """
                    :ivar group: Used to group system ports into
                        different groups within a common bus.
                    :ivar presence:
                    :ivar width: Number of bits required to represent
                        this port. Absence of this element indicates
                        unconstrained number of bits, i.e. the component
                        will define the number of bits in this port. The
                        logical numbering of the port starts at 0 to
                        width-1.
                    :ivar direction: If this element is present, the
                        direction of this port is restricted to the
                        specified value. The direction is relative to
                        the non-mirrored interface.
                    :ivar mode_constraints: Specifies default
                        constraints for the enclosing wire type port. If
                        the mirroredModeConstraints element is not
                        defined, then these constraints applied to this
                        port when it appears in a 'mode' bus interface
                        or a mirrored-'mode' bus interface. Otherwise
                        they only apply when the port appears in a
                        'mode' bus interface.
                    :ivar mirrored_mode_constraints: Specifies default
                        constraints for the enclosing wire type port
                        when it appears in a mirrored-'mode' bus
                        interface.
                    :ivar id:
                    """

                    group: str = field(
                        metadata={
                            "type": "Element",
                        }
                    )
                    presence: None | Presence = field(
                        default=None,
                        metadata={
                            "type": "Element",
                        },
                    )
                    width: None | UnsignedPositiveIntExpression = field(
                        default=None,
                        metadata={
                            "type": "Element",
                        },
                    )
                    direction: None | Direction = field(
                        default=None,
                        metadata={
                            "type": "Element",
                        },
                    )
                    mode_constraints: (
                        None | AbstractionDefPortConstraintsType
                    ) = field(
                        default=None,
                        metadata={
                            "name": "modeConstraints",
                            "type": "Element",
                        },
                    )
                    mirrored_mode_constraints: (
                        None | AbstractionDefPortConstraintsType
                    ) = field(
                        default=None,
                        metadata={
                            "name": "mirroredModeConstraints",
                            "type": "Element",
                        },
                    )
                    id: None | str = field(
                        default=None,
                        metadata={
                            "type": "Attribute",
                            "namespace": "http://www.w3.org/XML/1998/namespace",
                        },
                    )

                @dataclass(kw_only=True)
                class OnMaster:
                    """
                    :ivar presence:
                    :ivar width: Number of bits required to represent
                        this port. Absence of this element indicates
                        unconstrained number of bits, i.e. the component
                        will define the number of bits in this port. The
                        logical numbering of the port starts at 0 to
                        width-1.
                    :ivar direction: If this element is present, the
                        direction of this port is restricted to the
                        specified value. The direction is relative to
                        the non-mirrored interface.
                    :ivar mode_constraints: Specifies default
                        constraints for the enclosing wire type port. If
                        the mirroredModeConstraints element is not
                        defined, then these constraints applied to this
                        port when it appears in a 'mode' bus interface
                        or a mirrored-'mode' bus interface. Otherwise
                        they only apply when the port appears in a
                        'mode' bus interface.
                    :ivar mirrored_mode_constraints: Specifies default
                        constraints for the enclosing wire type port
                        when it appears in a mirrored-'mode' bus
                        interface.
                    """

                    presence: None | Presence = field(
                        default=None,
                        metadata={
                            "type": "Element",
                        },
                    )
                    width: None | UnsignedPositiveIntExpression = field(
                        default=None,
                        metadata={
                            "type": "Element",
                        },
                    )
                    direction: None | Direction = field(
                        default=None,
                        metadata={
                            "type": "Element",
                        },
                    )
                    mode_constraints: (
                        None | AbstractionDefPortConstraintsType
                    ) = field(
                        default=None,
                        metadata={
                            "name": "modeConstraints",
                            "type": "Element",
                        },
                    )
                    mirrored_mode_constraints: (
                        None | AbstractionDefPortConstraintsType
                    ) = field(
                        default=None,
                        metadata={
                            "name": "mirroredModeConstraints",
                            "type": "Element",
                        },
                    )

                @dataclass(kw_only=True)
                class OnSlave:
                    """
                    :ivar presence:
                    :ivar width: Number of bits required to represent
                        this port. Absence of this element indicates
                        unconstrained number of bits, i.e. the component
                        will define the number of bits in this port. The
                        logical numbering of the port starts at 0 to
                        width-1.
                    :ivar direction: If this element is present, the
                        direction of this port is restricted to the
                        specified value. The direction is relative to
                        the non-mirrored interface.
                    :ivar mode_constraints: Specifies default
                        constraints for the enclosing wire type port. If
                        the mirroredModeConstraints element is not
                        defined, then these constraints applied to this
                        port when it appears in a 'mode' bus interface
                        or a mirrored-'mode' bus interface. Otherwise
                        they only apply when the port appears in a
                        'mode' bus interface.
                    :ivar mirrored_mode_constraints: Specifies default
                        constraints for the enclosing wire type port
                        when it appears in a mirrored-'mode' bus
                        interface.
                    """

                    presence: None | Presence = field(
                        default=None,
                        metadata={
                            "type": "Element",
                        },
                    )
                    width: None | UnsignedPositiveIntExpression = field(
                        default=None,
                        metadata={
                            "type": "Element",
                        },
                    )
                    direction: None | Direction = field(
                        default=None,
                        metadata={
                            "type": "Element",
                        },
                    )
                    mode_constraints: (
                        None | AbstractionDefPortConstraintsType
                    ) = field(
                        default=None,
                        metadata={
                            "name": "modeConstraints",
                            "type": "Element",
                        },
                    )
                    mirrored_mode_constraints: (
                        None | AbstractionDefPortConstraintsType
                    ) = field(
                        default=None,
                        metadata={
                            "name": "mirroredModeConstraints",
                            "type": "Element",
                        },
                    )

            @dataclass(kw_only=True)
            class Transactional:
                """
                :ivar qualifier: The type of information this port
                    carries A transactional port can carry both address
                    and data information.
                :ivar on_system: Defines constraints for this port when
                    present in a system bus interface with a matching
                    group name.
                :ivar on_master: Defines constraints for this port when
                    present in a master bus interface.
                :ivar on_slave: Defines constraints for this port when
                    present in a slave bus interface.
                """

                qualifier: (
                    None
                    | AbstractionDefinition.Ports.Port.Transactional.Qualifier
                ) = field(
                    default=None,
                    metadata={
                        "type": "Element",
                    },
                )
                on_system: list[
                    AbstractionDefinition.Ports.Port.Transactional.OnSystem
                ] = field(
                    default_factory=list,
                    metadata={
                        "name": "onSystem",
                        "type": "Element",
                    },
                )
                on_master: (
                    None
                    | AbstractionDefinition.Ports.Port.Transactional.OnMaster
                ) = field(
                    default=None,
                    metadata={
                        "name": "onMaster",
                        "type": "Element",
                    },
                )
                on_slave: (
                    None
                    | AbstractionDefinition.Ports.Port.Transactional.OnSlave
                ) = field(
                    default=None,
                    metadata={
                        "name": "onSlave",
                        "type": "Element",
                    },
                )

                @dataclass(kw_only=True)
                class Qualifier:
                    """
                    :ivar is_address: If this element is present, the
                        port contains address information.
                    :ivar is_data: If this element is present, the port
                        contains data information.
                    """

                    is_address: None | bool = field(
                        default=None,
                        metadata={
                            "name": "isAddress",
                            "type": "Element",
                        },
                    )
                    is_data: None | bool = field(
                        default=None,
                        metadata={
                            "name": "isData",
                            "type": "Element",
                        },
                    )

                @dataclass(kw_only=True)
                class OnSystem:
                    """
                    :ivar group: Used to group system ports into
                        different groups within a common bus.
                    :ivar presence:
                    :ivar initiative: If this element is present, the
                        type of access is restricted to the specified
                        value.
                    :ivar kind:
                    :ivar bus_width: If this element is present, the
                        width must match
                    :ivar protocol: If this element is present, the name
                        must match
                    :ivar id:
                    """

                    group: str = field(
                        metadata={
                            "type": "Element",
                        }
                    )
                    presence: None | Presence = field(
                        default=None,
                        metadata={
                            "type": "Element",
                        },
                    )
                    initiative: None | OnSystemInitiative = field(
                        default=None,
                        metadata={
                            "type": "Element",
                        },
                    )
                    kind: None | Kind = field(
                        default=None,
                        metadata={
                            "type": "Element",
                        },
                    )
                    bus_width: None | UnsignedPositiveIntExpression = field(
                        default=None,
                        metadata={
                            "name": "busWidth",
                            "type": "Element",
                        },
                    )
                    protocol: None | Protocol = field(
                        default=None,
                        metadata={
                            "type": "Element",
                        },
                    )
                    id: None | str = field(
                        default=None,
                        metadata={
                            "type": "Attribute",
                            "namespace": "http://www.w3.org/XML/1998/namespace",
                        },
                    )

                @dataclass(kw_only=True)
                class OnMaster:
                    """
                    :ivar presence:
                    :ivar initiative: If this element is present, the
                        type of access is restricted to the specified
                        value.
                    :ivar kind:
                    :ivar bus_width: If this element is present, the
                        width must match
                    :ivar protocol: If this element is present, the name
                        must match
                    """

                    presence: None | Presence = field(
                        default=None,
                        metadata={
                            "type": "Element",
                        },
                    )
                    initiative: None | OnMasterInitiative = field(
                        default=None,
                        metadata={
                            "type": "Element",
                        },
                    )
                    kind: None | Kind = field(
                        default=None,
                        metadata={
                            "type": "Element",
                        },
                    )
                    bus_width: None | UnsignedPositiveIntExpression = field(
                        default=None,
                        metadata={
                            "name": "busWidth",
                            "type": "Element",
                        },
                    )
                    protocol: None | Protocol = field(
                        default=None,
                        metadata={
                            "type": "Element",
                        },
                    )

                @dataclass(kw_only=True)
                class OnSlave:
                    """
                    :ivar presence:
                    :ivar initiative: If this element is present, the
                        type of access is restricted to the specified
                        value.
                    :ivar kind:
                    :ivar bus_width: If this element is present, the
                        width must match
                    :ivar protocol: If this element is present, the name
                        must match
                    """

                    presence: None | Presence = field(
                        default=None,
                        metadata={
                            "type": "Element",
                        },
                    )
                    initiative: None | OnSlaveInitiative = field(
                        default=None,
                        metadata={
                            "type": "Element",
                        },
                    )
                    kind: None | Kind = field(
                        default=None,
                        metadata={
                            "type": "Element",
                        },
                    )
                    bus_width: None | UnsignedPositiveIntExpression = field(
                        default=None,
                        metadata={
                            "name": "busWidth",
                            "type": "Element",
                        },
                    )
                    protocol: None | Protocol = field(
                        default=None,
                        metadata={
                            "type": "Element",
                        },
                    )


@dataclass(kw_only=True)
class AbstractorBusInterfaceType:
    """
    Type definition for a busInterface in a component.

    :ivar name: Unique name
    :ivar display_name:
    :ivar description:
    :ivar abstraction_types:
    :ivar parameters:
    :ivar vendor_extensions:
    :ivar other_attributes:
    """

    class Meta:
        name = "abstractorBusInterfaceType"

    name: str = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    display_name: None | DisplayName = field(
        default=None,
        metadata={
            "name": "displayName",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    abstraction_types: None | AbstractionTypes = field(
        default=None,
        metadata={
            "name": "abstractionTypes",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    parameters: None | Parameters = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    other_attributes: dict[str, str] = field(
        default_factory=dict,
        metadata={
            "type": "Attributes",
            "namespace": "##other",
        },
    )


@dataclass(kw_only=True)
class BankedSubspaceType:
    """
    Subspace references inside banks do not specify an address.

    :ivar name: Unique name
    :ivar display_name:
    :ivar description:
    :ivar is_present:
    :ivar parameters: Any parameters that may apply to the subspace
        reference.
    :ivar vendor_extensions:
    :ivar master_ref: For subspaceMap elements, this attribute
        identifies the master that contains the address space to be
        mapped.
    :ivar id:
    """

    class Meta:
        name = "bankedSubspaceType"

    name: None | str = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    display_name: None | DisplayName = field(
        default=None,
        metadata={
            "name": "displayName",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    is_present: None | IsPresent = field(
        default=None,
        metadata={
            "name": "isPresent",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    parameters: None | Parameters = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    master_ref: str = field(
        metadata={
            "name": "masterRef",
            "type": "Attribute",
        }
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )


@dataclass(kw_only=True)
class BusDefinition:
    """
    Defines the structural information associated with a bus type,
    independent of the abstraction level.

    :ivar vendor: Name of the vendor who supplies this file.
    :ivar library: Name of the logical library this element belongs to.
    :ivar name: The name of the object.
    :ivar version: Indicates the version of the named element.
    :ivar direct_connection: This element indicates that a master
        interface may be directly connected to a slave interface (under
        certain conditions) for busses of this type.
    :ivar broadcast: This element indicates that this bus definition
        supports 'broadcast' mode. This means that it is legal to make
        one-to-many interface connections.
    :ivar is_addressable: If true, indicates that this is an addressable
        bus.
    :ivar extends: Optional name of bus type that this bus definition is
        compatible with. This bus definition may change the definitions
        in the existing bus definition
    :ivar max_masters: Indicates the maximum number of masters this bus
        supports.  If this element is not present, the number of masters
        allowed is unbounded.
    :ivar max_slaves: Indicates the maximum number of slaves this bus
        supports.  If the element is not present, the number of slaves
        allowed is unbounded.
    :ivar system_group_names: Indicates the list of system group names
        that are defined for this bus definition.
    :ivar description:
    :ivar parameters:
    :ivar assertions:
    :ivar vendor_extensions:
    :ivar id:
    """

    class Meta:
        name = "busDefinition"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    vendor: str = field(
        metadata={
            "type": "Element",
        }
    )
    library: str = field(
        metadata={
            "type": "Element",
        }
    )
    name: str = field(
        metadata={
            "type": "Element",
        }
    )
    version: str = field(
        metadata={
            "type": "Element",
        }
    )
    direct_connection: bool = field(
        metadata={
            "name": "directConnection",
            "type": "Element",
        }
    )
    broadcast: None | bool = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    is_addressable: bool = field(
        metadata={
            "name": "isAddressable",
            "type": "Element",
        }
    )
    extends: None | LibraryRefType = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    max_masters: None | UnsignedIntExpression = field(
        default=None,
        metadata={
            "name": "maxMasters",
            "type": "Element",
        },
    )
    max_slaves: None | UnsignedIntExpression = field(
        default=None,
        metadata={
            "name": "maxSlaves",
            "type": "Element",
        },
    )
    system_group_names: None | BusDefinition.SystemGroupNames = field(
        default=None,
        metadata={
            "name": "systemGroupNames",
            "type": "Element",
        },
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    parameters: None | Parameters = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    assertions: None | Assertions = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )

    @dataclass(kw_only=True)
    class SystemGroupNames:
        """
        :ivar system_group_name: Indicates the name of a system group
            defined for this bus definition.
        """

        system_group_name: list[
            BusDefinition.SystemGroupNames.SystemGroupName
        ] = field(
            default_factory=list,
            metadata={
                "name": "systemGroupName",
                "type": "Element",
                "min_occurs": 1,
            },
        )

        @dataclass(kw_only=True)
        class SystemGroupName:
            value: str = field(default="")
            id: None | str = field(
                default=None,
                metadata={
                    "type": "Attribute",
                    "namespace": "http://www.w3.org/XML/1998/namespace",
                },
            )


@dataclass(kw_only=True)
class BusInterfaceType:
    """
    Type definition for a busInterface in a component.

    :ivar name: Unique name
    :ivar display_name:
    :ivar description:
    :ivar is_present:
    :ivar bus_type: The bus type of this interface. Refers to bus
        definition using vendor, library, name, version attributes along
        with any configurable element values needed to configure this
        interface.
    :ivar abstraction_types:
    :ivar master: If this element is present, the bus interface can
        serve as a master.  This element encapsulates additional
        information related to its role as master.
    :ivar slave: If this element is present, the bus interface can serve
        as a slave.
    :ivar system: If this element is present, the bus interface is a
        system interface, neither master nor slave, with a specific
        function on the bus.
    :ivar mirrored_slave: If this element is present, the bus interface
        represents a mirrored slave interface. All directional
        constraints on ports are reversed relative to the specification
        in the bus definition.
    :ivar mirrored_master: If this element is present, the bus interface
        represents a mirrored master interface. All directional
        constraints on ports are reversed relative to the specification
        in the bus definition.
    :ivar mirrored_system: If this element is present, the bus interface
        represents a mirrored system interface. All directional
        constraints on ports are reversed relative to the specification
        in the bus definition.
    :ivar monitor: Indicates that this is a (passive) monitor interface.
        All of the ports in the interface must be inputs. The type of
        interface to be monitored is specified with the required
        interfaceType attribute. The ipxact:group element must be
        specified if monitoring a system interface.
    :ivar connection_required: Indicates whether a connection to this
        interface is required for proper component functionality.
    :ivar bits_in_lau:
    :ivar bit_steering: Indicates whether bit steering should be used to
        map this interface onto a bus of different data width. Values
        are "on", "off" (defaults to "off").
    :ivar endianness: 'big': means the most significant element of any
        multi-element  data field is stored at the lowest memory
        address. 'little' means the least significant element of any
        multi-element data field is stored at the lowest memory address.
        If this element is not present the default is 'little' endian.
    :ivar parameters:
    :ivar vendor_extensions:
    :ivar other_attributes:
    """

    class Meta:
        name = "busInterfaceType"

    name: str = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    display_name: None | DisplayName = field(
        default=None,
        metadata={
            "name": "displayName",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    is_present: None | IsPresent = field(
        default=None,
        metadata={
            "name": "isPresent",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    bus_type: ConfigurableLibraryRefType = field(
        metadata={
            "name": "busType",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    abstraction_types: None | AbstractionTypes = field(
        default=None,
        metadata={
            "name": "abstractionTypes",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    master: None | BusInterfaceType.Master = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    slave: None | BusInterfaceType.Slave = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    system: None | BusInterfaceType.System = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    mirrored_slave: None | BusInterfaceType.MirroredSlave = field(
        default=None,
        metadata={
            "name": "mirroredSlave",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    mirrored_master: None | object = field(
        default=None,
        metadata={
            "name": "mirroredMaster",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    mirrored_system: None | BusInterfaceType.MirroredSystem = field(
        default=None,
        metadata={
            "name": "mirroredSystem",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    monitor: None | BusInterfaceType.Monitor = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    connection_required: None | bool = field(
        default=None,
        metadata={
            "name": "connectionRequired",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    bits_in_lau: None | BitsInLau = field(
        default=None,
        metadata={
            "name": "bitsInLau",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    bit_steering: None | ComplexBitSteeringExpression = field(
        default=None,
        metadata={
            "name": "bitSteering",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    endianness: None | EndianessType = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    parameters: None | Parameters = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    other_attributes: dict[str, str] = field(
        default_factory=dict,
        metadata={
            "type": "Attributes",
            "namespace": "##other",
        },
    )

    @dataclass(kw_only=True)
    class Master:
        """
        :ivar address_space_ref: If this master connects to an
            addressable bus, this element references the address space
            it maps to.
        """

        address_space_ref: None | BusInterfaceType.Master.AddressSpaceRef = (
            field(
                default=None,
                metadata={
                    "name": "addressSpaceRef",
                    "type": "Element",
                    "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                },
            )
        )

        @dataclass(kw_only=True)
        class AddressSpaceRef(AddrSpaceRefType):
            """
            :ivar base_address: Base of an address space.
            """

            base_address: None | SignedLongintExpression = field(
                default=None,
                metadata={
                    "name": "baseAddress",
                    "type": "Element",
                    "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                },
            )

    @dataclass(kw_only=True)
    class Slave:
        """
        :ivar memory_map_ref:
        :ivar transparent_bridge:
        :ivar file_set_ref_group: This reference is used to point the
            filesets that are associated with this slave port. Depending
            on the slave port function, there may be completely
            different software drivers associated with the different
            ports.
        """

        memory_map_ref: None | MemoryMapRef = field(
            default=None,
            metadata={
                "name": "memoryMapRef",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            },
        )
        transparent_bridge: list[TransparentBridge] = field(
            default_factory=list,
            metadata={
                "name": "transparentBridge",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            },
        )
        file_set_ref_group: list[BusInterfaceType.Slave.FileSetRefGroup] = (
            field(
                default_factory=list,
                metadata={
                    "name": "fileSetRefGroup",
                    "type": "Element",
                    "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                },
            )
        )

        @dataclass(kw_only=True)
        class FileSetRefGroup:
            """
            :ivar group: Abritray name assigned to the collections of
                fileSets.
            :ivar file_set_ref:
            :ivar id:
            """

            group: None | str = field(
                default=None,
                metadata={
                    "type": "Element",
                    "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                },
            )
            file_set_ref: list[FileSetRef] = field(
                default_factory=list,
                metadata={
                    "name": "fileSetRef",
                    "type": "Element",
                    "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                },
            )
            id: None | str = field(
                default=None,
                metadata={
                    "type": "Attribute",
                    "namespace": "http://www.w3.org/XML/1998/namespace",
                },
            )

    @dataclass(kw_only=True)
    class System:
        group: Group = field(
            metadata={
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            }
        )

    @dataclass(kw_only=True)
    class MirroredSlave:
        """
        :ivar base_addresses: Represents a set of remap base addresses.
        """

        base_addresses: None | BusInterfaceType.MirroredSlave.BaseAddresses = (
            field(
                default=None,
                metadata={
                    "name": "baseAddresses",
                    "type": "Element",
                    "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                },
            )
        )

        @dataclass(kw_only=True)
        class BaseAddresses:
            """
            :ivar remap_address: Base of an address block, expressed as
                the number of bitsInLAU from the containing
                busInterface. The state attribute indicates the name of
                the remap state for which this address is valid.
            :ivar range: The address range of mirrored slave, expressed
                as the number of bitsInLAU from the containing
                busInterface.
            """

            remap_address: list[
                BusInterfaceType.MirroredSlave.BaseAddresses.RemapAddress
            ] = field(
                default_factory=list,
                metadata={
                    "name": "remapAddress",
                    "type": "Element",
                    "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                    "min_occurs": 1,
                },
            )
            range: UnsignedPositiveLongintExpression = field(
                metadata={
                    "type": "Element",
                    "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                }
            )

            @dataclass(kw_only=True)
            class RemapAddress(UnsignedLongintExpression):
                """
                :ivar state: Name of the state in which this remapped
                    address range is valid
                :ivar id:
                """

                state: None | str = field(
                    default=None,
                    metadata={
                        "type": "Attribute",
                    },
                )
                id: None | str = field(
                    default=None,
                    metadata={
                        "type": "Attribute",
                        "namespace": "http://www.w3.org/XML/1998/namespace",
                    },
                )

    @dataclass(kw_only=True)
    class MirroredSystem:
        group: Group = field(
            metadata={
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            }
        )

    @dataclass(kw_only=True)
    class Monitor:
        """
        :ivar group: Indicates which system interface is being
            monitored. Name must match a group name present on one or
            more ports in the corresonding bus definition.
        :ivar interface_mode:
        """

        group: None | Group = field(
            default=None,
            metadata={
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            },
        )
        interface_mode: MonitorInterfaceMode = field(
            metadata={
                "name": "interfaceMode",
                "type": "Attribute",
            }
        )


@dataclass(kw_only=True)
class ComponentInstantiationType:
    """
    Component instantiation type.

    :ivar name: Unique name
    :ivar display_name:
    :ivar description:
    :ivar is_virtual: When true, indicates that this component should
        not be netlisted.
    :ivar language: The hardware description language used such as
        "verilog" or "vhdl". If the attribute "strict" is "true", this
        value must match the language being generated for the design.
    :ivar library_name: A string specifying the library name in which
        the model should be compiled. If the libraryName element is not
        present then its value defaults to “work”.
    :ivar package_name: A string describing the VHDL package containing
        the interface of the model. If the packageName element is not
        present then its value defaults to the component VLNV name
        concatenated with postfix “_cmp_pkg” which stands for component
        package.
    :ivar module_name: A string describing the Verilog, SystemVerilog,
        or SystemC module name or the VHDL entity name. If the
        moduleName is not present then its value defaults to the
        component VLNV name
    :ivar architecture_name: A string describing the VHDL architecture
        name. If the architectureName element is not present then its
        value defaults to “rtl”.
    :ivar configuration_name: A string describing the Verilog,
        SystemVerilog, or VHDL configuration name. If the
        configurationName element is not present then its value defaults
        to the design configuration VLNV name of the design
        configuration associated with the active hierarchical view or,
        if there is no active hierarchical view, to the component VLNV
        name concatenated with postfix “_rtl_cfg”.
    :ivar module_parameters: Model parameter name value pairs container
    :ivar default_file_builder: Default command and flags used to build
        derived files from the sourceName files in the referenced file
        sets.
    :ivar file_set_ref:
    :ivar constraint_set_ref:
    :ivar whitebox_element_refs: Container for white box element
        references.
    :ivar parameters:
    :ivar vendor_extensions:
    :ivar id:
    """

    class Meta:
        name = "componentInstantiationType"

    name: str = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    display_name: None | DisplayName = field(
        default=None,
        metadata={
            "name": "displayName",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    is_virtual: None | bool = field(
        default=None,
        metadata={
            "name": "isVirtual",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    language: None | LanguageType = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    library_name: None | object = field(
        default=None,
        metadata={
            "name": "libraryName",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    package_name: None | str = field(
        default=None,
        metadata={
            "name": "packageName",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    module_name: None | str = field(
        default=None,
        metadata={
            "name": "moduleName",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    architecture_name: None | str = field(
        default=None,
        metadata={
            "name": "architectureName",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    configuration_name: None | str = field(
        default=None,
        metadata={
            "name": "configurationName",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    module_parameters: None | ComponentInstantiationType.ModuleParameters = (
        field(
            default=None,
            metadata={
                "name": "moduleParameters",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            },
        )
    )
    default_file_builder: list[FileBuilderType] = field(
        default_factory=list,
        metadata={
            "name": "defaultFileBuilder",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    file_set_ref: list[FileSetRef] = field(
        default_factory=list,
        metadata={
            "name": "fileSetRef",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    constraint_set_ref: list[ConstraintSetRef] = field(
        default_factory=list,
        metadata={
            "name": "constraintSetRef",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    whitebox_element_refs: (
        None | ComponentInstantiationType.WhiteboxElementRefs
    ) = field(
        default=None,
        metadata={
            "name": "whiteboxElementRefs",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    parameters: None | Parameters = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )

    @dataclass(kw_only=True)
    class ModuleParameters:
        """
        :ivar module_parameter: A module parameter name value pair. The
            name is given in an attribute. The value is the element
            value. The dataType (applicable to high level modeling) is
            given in the dataType attribute. For hardware based models,
            the name should be identical to the RTL (VHDL generic or
            Verilog parameter). The usageType attribute indicates how
            the model parameter is to be used.
        """

        module_parameter: list[ModuleParameterType] = field(
            default_factory=list,
            metadata={
                "name": "moduleParameter",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                "min_occurs": 1,
            },
        )

    @dataclass(kw_only=True)
    class WhiteboxElementRefs:
        """
        :ivar whitebox_element_ref: Reference to a white box element
            which is visible within this view.
        """

        whitebox_element_ref: list[WhiteboxElementRefType] = field(
            default_factory=list,
            metadata={
                "name": "whiteboxElementRef",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            },
        )


@dataclass(kw_only=True)
class Design:
    """
    Root element for a platform design.

    :ivar vendor: Name of the vendor who supplies this file.
    :ivar library: Name of the logical library this element belongs to.
    :ivar name: The name of the object.
    :ivar version: Indicates the version of the named element.
    :ivar component_instances:
    :ivar interconnections:
    :ivar ad_hoc_connections:
    :ivar description:
    :ivar parameters:
    :ivar assertions:
    :ivar vendor_extensions:
    :ivar id:
    """

    class Meta:
        name = "design"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    vendor: str = field(
        metadata={
            "type": "Element",
        }
    )
    library: str = field(
        metadata={
            "type": "Element",
        }
    )
    name: str = field(
        metadata={
            "type": "Element",
        }
    )
    version: str = field(
        metadata={
            "type": "Element",
        }
    )
    component_instances: None | ComponentInstances = field(
        default=None,
        metadata={
            "name": "componentInstances",
            "type": "Element",
        },
    )
    interconnections: None | Interconnections = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    ad_hoc_connections: None | AdHocConnections = field(
        default=None,
        metadata={
            "name": "adHocConnections",
            "type": "Element",
        },
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    parameters: None | Parameters = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    assertions: None | Assertions = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )


@dataclass(kw_only=True)
class DesignConfiguration:
    """
    Top level element for describing the current configuration of a design.

    Does not describe instance parameterization.

    :ivar vendor: Name of the vendor who supplies this file.
    :ivar library: Name of the logical library this element belongs to.
    :ivar name: The name of the object.
    :ivar version: Indicates the version of the named element.
    :ivar design_ref: The design to which this configuration applies
    :ivar generator_chain_configuration: Contains the configurable
        information associated with a generatorChain and its generators.
        Note that configurable information for generators associated
        with components is stored in the design file.
    :ivar interconnection_configuration: Contains the information about
        the abstractors required to cross between two interfaces at with
        different abstractionDefs.
    :ivar view_configuration: Contains the active views for each
        instance in the design
    :ivar description:
    :ivar parameters:
    :ivar assertions:
    :ivar vendor_extensions:
    :ivar id:
    """

    class Meta:
        name = "designConfiguration"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    vendor: str = field(
        metadata={
            "type": "Element",
        }
    )
    library: str = field(
        metadata={
            "type": "Element",
        }
    )
    name: str = field(
        metadata={
            "type": "Element",
        }
    )
    version: str = field(
        metadata={
            "type": "Element",
        }
    )
    design_ref: None | LibraryRefType = field(
        default=None,
        metadata={
            "name": "designRef",
            "type": "Element",
        },
    )
    generator_chain_configuration: list[ConfigurableLibraryRefType] = field(
        default_factory=list,
        metadata={
            "name": "generatorChainConfiguration",
            "type": "Element",
        },
    )
    interconnection_configuration: list[
        DesignConfiguration.InterconnectionConfiguration
    ] = field(
        default_factory=list,
        metadata={
            "name": "interconnectionConfiguration",
            "type": "Element",
        },
    )
    view_configuration: list[DesignConfiguration.ViewConfiguration] = field(
        default_factory=list,
        metadata={
            "name": "viewConfiguration",
            "type": "Element",
        },
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    parameters: None | Parameters = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    assertions: None | Assertions = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )

    @dataclass(kw_only=True)
    class InterconnectionConfiguration:
        """
        :ivar is_present:
        :ivar interconnection_ref: Reference to the interconnection
            name, monitor interconnection name or possibly a
            hierConnection interfaceName in a design file.
        :ivar abstractor_instances: List of abstractor-instances for
            this interconnection. Multiple abstractor-instances elements
            may be present for a 1-to-many (broadcast) interconnection.
            In that case, the optional interfaceRef elements must
            reference non-overlapping interfaces from the 'many' side of
            the interconnection.
        :ivar id:
        """

        is_present: None | IsPresent = field(
            default=None,
            metadata={
                "name": "isPresent",
                "type": "Element",
            },
        )
        interconnection_ref: str = field(
            metadata={
                "name": "interconnectionRef",
                "type": "Element",
            }
        )
        abstractor_instances: list[
            DesignConfiguration.InterconnectionConfiguration.AbstractorInstances
        ] = field(
            default_factory=list,
            metadata={
                "name": "abstractorInstances",
                "type": "Element",
                "min_occurs": 1,
            },
        )
        id: None | str = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.w3.org/XML/1998/namespace",
            },
        )

        @dataclass(kw_only=True)
        class AbstractorInstances:
            """
            :ivar is_present:
            :ivar interface_ref: Defines the broadcast endpoint to which
                this chain of abstractors applies.
            :ivar abstractor_instance: Element to hold a the abstractor
                reference, the configuration and viewName. If multiple
                elements are present then the order is the order in
                which the abstractors should be chained together.
            """

            is_present: None | IsPresent = field(
                default=None,
                metadata={
                    "name": "isPresent",
                    "type": "Element",
                },
            )
            interface_ref: list[
                DesignConfiguration.InterconnectionConfiguration.AbstractorInstances.InterfaceRef
            ] = field(
                default_factory=list,
                metadata={
                    "name": "interfaceRef",
                    "type": "Element",
                },
            )
            abstractor_instance: list[
                DesignConfiguration.InterconnectionConfiguration.AbstractorInstances.AbstractorInstance
            ] = field(
                default_factory=list,
                metadata={
                    "name": "abstractorInstance",
                    "type": "Element",
                    "min_occurs": 1,
                },
            )

            @dataclass(kw_only=True)
            class InterfaceRef:
                """
                :ivar is_present:
                :ivar component_ref: Reference to a component instance
                    nane.
                :ivar bus_ref: Reference to a component bus interface
                    name.
                """

                is_present: None | IsPresent = field(
                    default=None,
                    metadata={
                        "name": "isPresent",
                        "type": "Element",
                    },
                )
                component_ref: str = field(
                    metadata={
                        "name": "componentRef",
                        "type": "Attribute",
                    }
                )
                bus_ref: str = field(
                    metadata={
                        "name": "busRef",
                        "type": "Attribute",
                    }
                )

            @dataclass(kw_only=True)
            class AbstractorInstance:
                """
                :ivar instance_name: Instance name for the abstractor
                :ivar display_name:
                :ivar description:
                :ivar abstractor_ref: Abstractor reference
                :ivar view_name: The name of the active view for this
                    abstractor instance.
                :ivar id:
                """

                instance_name: str = field(
                    metadata={
                        "name": "instanceName",
                        "type": "Element",
                    }
                )
                display_name: None | DisplayName = field(
                    default=None,
                    metadata={
                        "name": "displayName",
                        "type": "Element",
                    },
                )
                description: None | Description = field(
                    default=None,
                    metadata={
                        "type": "Element",
                    },
                )
                abstractor_ref: ConfigurableLibraryRefType = field(
                    metadata={
                        "name": "abstractorRef",
                        "type": "Element",
                    }
                )
                view_name: str = field(
                    metadata={
                        "name": "viewName",
                        "type": "Element",
                    }
                )
                id: None | str = field(
                    default=None,
                    metadata={
                        "type": "Attribute",
                        "namespace": "http://www.w3.org/XML/1998/namespace",
                    },
                )

    @dataclass(kw_only=True)
    class ViewConfiguration:
        """
        :ivar instance_name:
        :ivar is_present:
        :ivar view: The selected view for the instance.
        :ivar id:
        """

        instance_name: InstanceName = field(
            metadata={
                "name": "instanceName",
                "type": "Element",
            }
        )
        is_present: None | IsPresent = field(
            default=None,
            metadata={
                "name": "isPresent",
                "type": "Element",
            },
        )
        view: DesignConfiguration.ViewConfiguration.View = field(
            metadata={
                "type": "Element",
            }
        )
        id: None | str = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.w3.org/XML/1998/namespace",
            },
        )

        @dataclass(kw_only=True)
        class View:
            """
            :ivar configurable_element_values: Parameter values to set
                in the selected configuredView.
            :ivar view_ref:
            """

            configurable_element_values: None | ConfigurableElementValues = (
                field(
                    default=None,
                    metadata={
                        "name": "configurableElementValues",
                        "type": "Element",
                    },
                )
            )
            view_ref: str = field(
                metadata={
                    "name": "viewRef",
                    "type": "Attribute",
                }
            )


@dataclass(kw_only=True)
class DesignConfigurationInstantiationType:
    """
    Design configuration instantiation type.

    :ivar name: Unique name
    :ivar display_name:
    :ivar description:
    :ivar language: The hardware description language used such as
        "verilog" or "vhdl". If the attribute "strict" is "true", this
        value must match the language being generated for the design.
    :ivar design_configuration_ref: References an IP-XACT design
        configuration document (by VLNV) that provides a configuration
        for the component's design.
    :ivar parameters:
    :ivar vendor_extensions:
    :ivar id:
    """

    class Meta:
        name = "designConfigurationInstantiationType"

    name: str = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    display_name: None | DisplayName = field(
        default=None,
        metadata={
            "name": "displayName",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    language: None | LanguageType = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    design_configuration_ref: ConfigurableLibraryRefType = field(
        metadata={
            "name": "designConfigurationRef",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    parameters: None | Parameters = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )


@dataclass(kw_only=True)
class ExecutableImage:
    """
    Specifies an executable software image to be loaded into a processors
    address space.

    The format of the image is not specified. It could, for example, be an
    ELF loadfile, or it could be raw binary or ascii hex data for loading
    directly into a memory model instance.

    :ivar name: Unique name
    :ivar display_name:
    :ivar description:
    :ivar parameters: Additional information about the load module, e.g.
        stack base addresses, table addresses, etc.
    :ivar language_tools: Default commands and flags for software
        language tools needed to build the executable image.
    :ivar file_set_ref_group: Contains a group of file set references
        that indicates the set of file sets complying with the tool set
        of the current executable image.
    :ivar vendor_extensions:
    :ivar image_id: Unique ID for the executableImage, referenced in
        fileSet/function/fileRef
    :ivar image_type: Open element to describe the type of image. The
        contents is model and/or generator specific.
    :ivar id:
    """

    class Meta:
        name = "executableImage"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    name: str = field(
        metadata={
            "type": "Element",
        }
    )
    display_name: None | DisplayName = field(
        default=None,
        metadata={
            "name": "displayName",
            "type": "Element",
        },
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    parameters: None | Parameters = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    language_tools: None | ExecutableImage.LanguageTools = field(
        default=None,
        metadata={
            "name": "languageTools",
            "type": "Element",
        },
    )
    file_set_ref_group: None | ExecutableImage.FileSetRefGroup = field(
        default=None,
        metadata={
            "name": "fileSetRefGroup",
            "type": "Element",
        },
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
        },
    )
    image_id: str = field(
        metadata={
            "name": "imageId",
            "type": "Attribute",
        }
    )
    image_type: None | str = field(
        default=None,
        metadata={
            "name": "imageType",
            "type": "Attribute",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )

    @dataclass(kw_only=True)
    class LanguageTools:
        """
        :ivar file_builder: A generic placeholder for any file builder
            like compilers and assemblers.  It contains the file types
            to which the command should be applied, and the flags to be
            used with that command.
        :ivar linker:
        :ivar linker_flags:
        :ivar linker_command_file:
        """

        file_builder: list[ExecutableImage.LanguageTools.FileBuilder] = field(
            default_factory=list,
            metadata={
                "name": "fileBuilder",
                "type": "Element",
            },
        )
        linker: None | StringExpression = field(
            default=None,
            metadata={
                "type": "Element",
            },
        )
        linker_flags: None | StringExpression = field(
            default=None,
            metadata={
                "name": "linkerFlags",
                "type": "Element",
            },
        )
        linker_command_file: None | LinkerCommandFile = field(
            default=None,
            metadata={
                "name": "linkerCommandFile",
                "type": "Element",
            },
        )

        @dataclass(kw_only=True)
        class FileBuilder:
            """
            :ivar file_type:
            :ivar command: Default command used to build files of the
                specified fileType.
            :ivar flags: Flags given to the build command when building
                files of this type.
            :ivar replace_default_flags: If true, replace any default
                flags value with the value in the sibling flags element.
                Otherwise, append the contents of the sibling flags
                element to any default flags value. If the value is true
                and the "flags" element is empty or missing, this will
                have the result of clearing any default flags value.
            :ivar vendor_extensions:
            :ivar id:
            """

            file_type: FileType = field(
                metadata={
                    "name": "fileType",
                    "type": "Element",
                }
            )
            command: StringExpression = field(
                metadata={
                    "type": "Element",
                }
            )
            flags: None | StringExpression = field(
                default=None,
                metadata={
                    "type": "Element",
                },
            )
            replace_default_flags: None | UnsignedBitExpression = field(
                default=None,
                metadata={
                    "name": "replaceDefaultFlags",
                    "type": "Element",
                },
            )
            vendor_extensions: None | VendorExtensions = field(
                default=None,
                metadata={
                    "name": "vendorExtensions",
                    "type": "Element",
                },
            )
            id: None | str = field(
                default=None,
                metadata={
                    "type": "Attribute",
                    "namespace": "http://www.w3.org/XML/1998/namespace",
                },
            )

    @dataclass(kw_only=True)
    class FileSetRefGroup:
        file_set_ref: list[FileSetRef] = field(
            default_factory=list,
            metadata={
                "name": "fileSetRef",
                "type": "Element",
                "min_occurs": 1,
            },
        )


@dataclass(kw_only=True)
class FieldType:
    """
    A field within a register.

    :ivar name: Unique name
    :ivar display_name:
    :ivar description:
    :ivar access_handles:
    :ivar is_present:
    :ivar bit_offset: Offset of this field's bit 0 from bit 0 of the
        register.
    :ivar resets:
    :ivar type_identifier: Identifier name used to indicate that
        multiple field elements contain the exact same information for
        the elements in the fieldDefinitionGroup.
    :ivar bit_width: Width of the field in bits.
    :ivar volatile: Indicates whether the data is volatile. The presumed
        value is 'false' if not present.
    :ivar access:
    :ivar enumerated_values:
    :ivar modified_write_value: If present this element describes the
        modification of field data caused by a write operation.
        'oneToClear' means that in a bitwise fashion each write data bit
        of a one will clear the corresponding bit in the field.
        'oneToSet' means that in a bitwise fashion each write data bit
        of a one will set the corresponding bit in the field.
        'oneToToggle' means that in a bitwise fashion each write data
        bit of a one will toggle the corresponding bit in the field.
        'zeroToClear' means that in a bitwise fashion each write data
        bit of a zero will clear the corresponding bit in the field.
        'zeroToSet' means that in a bitwise fashion each write data bit
        of a zero will set the corresponding bit in the field.
        'zeroToToggle' means that in a bitwise fashion each write data
        bit of a zero will toggle the corresponding bit in the field.
        'clear' means any write to this field clears the field. 'set'
        means any write to the field sets the field. 'modify' means any
        write to this field may modify that data. If this element is not
        present the write operation data is written.
    :ivar write_value_constraint: The legal values that may be written
        to a field. If not specified the legal values are not specified.
    :ivar read_action: A list of possible actions for a read to set the
        field after the read. 'clear' means that after a read the field
        is cleared. 'set' means that after a read the field is set.
        'modify' means after a read the field is modified. If not
        present the field value is not modified after a read.
    :ivar testable: Can the field be tested with an automated register
        test routine. The presumed value is true if not specified.
    :ivar reserved: Indicates that the field should be documented as
        reserved. The presumed value is 'false' if not present.
    :ivar parameters:
    :ivar vendor_extensions:
    :ivar id:
    :ivar field_id: A unique identifier within a component for a field.
    """

    class Meta:
        name = "fieldType"

    name: str = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    display_name: None | DisplayName = field(
        default=None,
        metadata={
            "name": "displayName",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    access_handles: None | FieldType.AccessHandles = field(
        default=None,
        metadata={
            "name": "accessHandles",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    is_present: None | IsPresent = field(
        default=None,
        metadata={
            "name": "isPresent",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    bit_offset: UnsignedIntExpression = field(
        metadata={
            "name": "bitOffset",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    resets: None | FieldType.Resets = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    type_identifier: None | str = field(
        default=None,
        metadata={
            "name": "typeIdentifier",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    bit_width: UnsignedPositiveIntExpression = field(
        metadata={
            "name": "bitWidth",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    volatile: None | Volatile = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    access: None | Access = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    enumerated_values: None | EnumeratedValues = field(
        default=None,
        metadata={
            "name": "enumeratedValues",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    modified_write_value: None | FieldType.ModifiedWriteValue = field(
        default=None,
        metadata={
            "name": "modifiedWriteValue",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    write_value_constraint: None | WriteValueConstraintType = field(
        default=None,
        metadata={
            "name": "writeValueConstraint",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    read_action: None | FieldType.ReadAction = field(
        default=None,
        metadata={
            "name": "readAction",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    testable: None | FieldType.Testable = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    reserved: None | UnsignedBitExpression = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    parameters: None | Parameters = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )
    field_id: None | str = field(
        default=None,
        metadata={
            "name": "fieldID",
            "type": "Attribute",
        },
    )

    @dataclass(kw_only=True)
    class AccessHandles:
        access_handle: list[NonIndexedLeafAccessHandle] = field(
            default_factory=list,
            metadata={
                "name": "accessHandle",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                "min_occurs": 1,
            },
        )

    @dataclass(kw_only=True)
    class Resets:
        """
        :ivar reset: BitField reset value
        """

        reset: list[Reset] = field(
            default_factory=list,
            metadata={
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                "min_occurs": 1,
            },
        )

    @dataclass(kw_only=True)
    class ModifiedWriteValue:
        value: ModifiedWriteValueType = field()
        modify: None | str = field(
            default=None,
            metadata={
                "type": "Attribute",
            },
        )

    @dataclass(kw_only=True)
    class ReadAction:
        value: ReadActionType = field()
        modify: None | str = field(
            default=None,
            metadata={
                "type": "Attribute",
            },
        )

    @dataclass(kw_only=True)
    class Testable:
        """
        :ivar value:
        :ivar test_constraint: Constraint for an automated register test
            routine. 'unconstrained' (default) means may read and write
            all legal values. 'restore' means may read and write legal
            values but the value must be restored to the initially read
            value before accessing another register. 'writeAsRead' has
            limitations on testability where only the value read before
            a write may be written to the field. 'readOnly' has
            limitations on testability where values may only be read
            from the field.
        """

        value: bool = field()
        test_constraint: TestableTestConstraint = field(
            default=TestableTestConstraint.UNCONSTRAINED,
            metadata={
                "name": "testConstraint",
                "type": "Attribute",
            },
        )


@dataclass(kw_only=True)
class GeneratorType:
    """
    Types of generators.

    :ivar name: Unique name
    :ivar display_name:
    :ivar description:
    :ivar phase:
    :ivar parameters:
    :ivar api_type: Indicates the type of API used by the generator.
        Valid value are TGI_2009, TGI_2014_BASE, TGI_2014_EXTENDED, and
        none. If this element is not present, TGI_2014_BASE is assumed.
        The type TGI_2009 indicates a generator using the 1685-2009
        version of the TGI API. This is not part of the 1685-2014
        version of the standard and may not be supported by Design
        Environments.
    :ivar transport_methods:
    :ivar generator_exe: The pathname to the executable file that
        implements the generator
    :ivar vendor_extensions:
    :ivar hidden: If this attribute is true then the generator should
        not be presented to the user, it may be part of a chain and has
        no useful meaning when invoked standalone.
    :ivar id:
    """

    class Meta:
        name = "generatorType"

    name: str = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    display_name: None | DisplayName = field(
        default=None,
        metadata={
            "name": "displayName",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    phase: None | Phase = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    parameters: None | Parameters = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    api_type: None | GeneratorType.ApiType = field(
        default=None,
        metadata={
            "name": "apiType",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    transport_methods: None | GeneratorType.TransportMethods = field(
        default=None,
        metadata={
            "name": "transportMethods",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    generator_exe: IpxactUri = field(
        metadata={
            "name": "generatorExe",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    hidden: bool = field(
        default=False,
        metadata={
            "type": "Attribute",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )

    @dataclass(kw_only=True)
    class ApiType:
        value: ApiType = field()
        id: None | str = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.w3.org/XML/1998/namespace",
            },
        )

    @dataclass(kw_only=True)
    class TransportMethods:
        """
        :ivar transport_method: Defines a SOAP transport protocol other
            than HTTP which is supported by this generator. The only
            other currently supported protocol is 'file'.
        :ivar id:
        """

        transport_method: GeneratorType.TransportMethods.TransportMethod = field(
            metadata={
                "name": "transportMethod",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            }
        )
        id: None | str = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.w3.org/XML/1998/namespace",
            },
        )

        @dataclass(kw_only=True)
        class TransportMethod:
            value: TransportMethodType = field()
            id: None | str = field(
                default=None,
                metadata={
                    "type": "Attribute",
                    "namespace": "http://www.w3.org/XML/1998/namespace",
                },
            )


@dataclass(kw_only=True)
class IndirectInterfaceType:
    """
    Type definition for a indirectInterface in a component.

    :ivar name: Unique name
    :ivar display_name:
    :ivar description:
    :ivar indirect_address_ref:
    :ivar indirect_data_ref:
    :ivar memory_map_ref: A reference to a memoryMap. This memoryMap is
        indirectly accessible through this interface.
    :ivar transparent_bridge:
    :ivar bits_in_lau:
    :ivar endianness: 'big': means the most significant element of any
        multi-element  data field is stored at the lowest memory
        address. 'little' means the least significant element of any
        multi-element data field is stored at the lowest memory address.
        If this element is not present the default is 'little' endian.
    :ivar parameters:
    :ivar vendor_extensions:
    :ivar any_attributes:
    """

    class Meta:
        name = "indirectInterfaceType"

    name: str = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    display_name: None | DisplayName = field(
        default=None,
        metadata={
            "name": "displayName",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    indirect_address_ref: IndirectAddressRef = field(
        metadata={
            "name": "indirectAddressRef",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    indirect_data_ref: IndirectDataRef = field(
        metadata={
            "name": "indirectDataRef",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    memory_map_ref: None | str = field(
        default=None,
        metadata={
            "name": "memoryMapRef",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    transparent_bridge: list[TransparentBridge] = field(
        default_factory=list,
        metadata={
            "name": "transparentBridge",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    bits_in_lau: None | BitsInLau = field(
        default=None,
        metadata={
            "name": "bitsInLau",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    endianness: None | EndianessType = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    parameters: None | Parameters = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    any_attributes: dict[str, str] = field(
        default_factory=dict,
        metadata={
            "type": "Attributes",
            "namespace": "##any",
        },
    )


@dataclass(kw_only=True)
class SubspaceRefType:
    """
    Address subspace type.

    Its subspaceReference attribute references the subspace from which the
    dimensions are taken.

    :ivar name: Unique name
    :ivar display_name:
    :ivar description:
    :ivar is_present:
    :ivar base_address:
    :ivar parameters: Any parameters that may apply to the subspace
        reference.
    :ivar vendor_extensions:
    :ivar master_ref: For subspaceMap elements, this attribute
        identifies the master that contains the address space to be
        mapped.
    :ivar segment_ref: Refernce to a segment of the addressSpace of the
        masterRef attribute.
    """

    class Meta:
        name = "subspaceRefType"

    name: str = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    display_name: None | DisplayName = field(
        default=None,
        metadata={
            "name": "displayName",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    is_present: None | IsPresent = field(
        default=None,
        metadata={
            "name": "isPresent",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    base_address: BaseAddress = field(
        metadata={
            "name": "baseAddress",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    parameters: None | Parameters = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    master_ref: str = field(
        metadata={
            "name": "masterRef",
            "type": "Attribute",
        }
    )
    segment_ref: None | str = field(
        default=None,
        metadata={
            "name": "segmentRef",
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class TypeParameters:
    """
    list of port type parameters (e.g. template or constructor parameters
    for a systemC port or socket).
    """

    class Meta:
        name = "typeParameters"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    type_parameter: list[TypeParameter] = field(
        default_factory=list,
        metadata={
            "name": "typeParameter",
            "type": "Element",
        },
    )
    service_type_def: list[ServiceTypeDef] = field(
        default_factory=list,
        metadata={
            "name": "serviceTypeDef",
            "type": "Element",
        },
    )


@dataclass(kw_only=True)
class WhiteboxElementType:
    """
    Defines a white box reference point within the component.

    :ivar name: Unique name
    :ivar display_name:
    :ivar description:
    :ivar is_present:
    :ivar whitebox_type: Indicates the type of the element. The pin and
        signal types refer to elements within the HDL description. The
        register type refers to a register in the memory map. The
        interface type refers to a group of signals addressed as a
        single unit.
    :ivar driveable: If true, indicates that the white box element can
        be driven (e.g. have a new value forced into it).
    :ivar parameters:
    :ivar vendor_extensions:
    :ivar id:
    """

    class Meta:
        name = "whiteboxElementType"

    name: str = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    display_name: None | DisplayName = field(
        default=None,
        metadata={
            "name": "displayName",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    is_present: None | IsPresent = field(
        default=None,
        metadata={
            "name": "isPresent",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    whitebox_type: SimpleWhiteboxType = field(
        metadata={
            "name": "whiteboxType",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    driveable: None | bool = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    parameters: None | Parameters = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )


@dataclass(kw_only=True)
class AlternateRegisters:
    """
    Alternate definitions for the current register.

    :ivar alternate_register: Alternate definition for the current
        register
    """

    class Meta:
        name = "alternateRegisters"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    alternate_register: list[AlternateRegisters.AlternateRegister] = field(
        default_factory=list,
        metadata={
            "name": "alternateRegister",
            "type": "Element",
            "min_occurs": 1,
        },
    )

    @dataclass(kw_only=True)
    class AlternateRegister:
        """
        :ivar name: Unique name
        :ivar display_name:
        :ivar description:
        :ivar access_handles:
        :ivar is_present:
        :ivar alternate_groups: Defines a list of grouping names that
            this register description belongs.
        :ivar type_identifier: Identifier name used to indicate that
            multiple register elements contain the exact same
            information for the elements in the
            alternateRegisterDefinitionGroup.
        :ivar volatile:
        :ivar access:
        :ivar field_value: Describes individual bit fields within the
            register.
        :ivar parameters:
        :ivar vendor_extensions:
        :ivar id:
        """

        name: str = field(
            metadata={
                "type": "Element",
            }
        )
        display_name: None | DisplayName = field(
            default=None,
            metadata={
                "name": "displayName",
                "type": "Element",
            },
        )
        description: None | Description = field(
            default=None,
            metadata={
                "type": "Element",
            },
        )
        access_handles: (
            None | AlternateRegisters.AlternateRegister.AccessHandles
        ) = field(
            default=None,
            metadata={
                "name": "accessHandles",
                "type": "Element",
            },
        )
        is_present: None | IsPresent = field(
            default=None,
            metadata={
                "name": "isPresent",
                "type": "Element",
            },
        )
        alternate_groups: AlternateRegisters.AlternateRegister.AlternateGroups = field(
            metadata={
                "name": "alternateGroups",
                "type": "Element",
            }
        )
        type_identifier: None | str = field(
            default=None,
            metadata={
                "name": "typeIdentifier",
                "type": "Element",
            },
        )
        volatile: None | Volatile = field(
            default=None,
            metadata={
                "type": "Element",
            },
        )
        access: None | Access = field(
            default=None,
            metadata={
                "type": "Element",
            },
        )
        field_value: list[FieldType] = field(
            default_factory=list,
            metadata={
                "name": "field",
                "type": "Element",
                "min_occurs": 1,
            },
        )
        parameters: None | Parameters = field(
            default=None,
            metadata={
                "type": "Element",
            },
        )
        vendor_extensions: None | VendorExtensions = field(
            default=None,
            metadata={
                "name": "vendorExtensions",
                "type": "Element",
            },
        )
        id: None | str = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.w3.org/XML/1998/namespace",
            },
        )

        @dataclass(kw_only=True)
        class AccessHandles:
            access_handle: list[IndexedAccessHandle] = field(
                default_factory=list,
                metadata={
                    "name": "accessHandle",
                    "type": "Element",
                    "min_occurs": 1,
                },
            )

        @dataclass(kw_only=True)
        class AlternateGroups:
            """
            :ivar alternate_group: Defines a grouping name that this
                register description belongs.
            :ivar id:
            """

            alternate_group: list[
                AlternateRegisters.AlternateRegister.AlternateGroups.AlternateGroup
            ] = field(
                default_factory=list,
                metadata={
                    "name": "alternateGroup",
                    "type": "Element",
                    "min_occurs": 1,
                },
            )
            id: None | str = field(
                default=None,
                metadata={
                    "type": "Attribute",
                    "namespace": "http://www.w3.org/XML/1998/namespace",
                },
            )

            @dataclass(kw_only=True)
            class AlternateGroup:
                value: str = field(default="")
                id: None | str = field(
                    default=None,
                    metadata={
                        "type": "Attribute",
                        "namespace": "http://www.w3.org/XML/1998/namespace",
                    },
                )


@dataclass(kw_only=True)
class BusInterface(BusInterfaceType):
    """
    Describes one of the bus interfaces supported by this component.
    """

    class Meta:
        name = "busInterface"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"


@dataclass(kw_only=True)
class Generator(GeneratorType):
    """
    Specifies a set of generators.
    """

    class Meta:
        name = "generator"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"


@dataclass(kw_only=True)
class IndirectInterface(IndirectInterfaceType):
    """
    Describes one of the bus interfaces supported by this component.
    """

    class Meta:
        name = "indirectInterface"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"


@dataclass(kw_only=True)
class InstanceGeneratorType(GeneratorType):
    """
    :ivar group: An identifier to specify the generator group. This is
        used by generator chains for selecting which generators to run.
    :ivar scope: The scope attribute applies to component generators and
        specifies whether the generator should be run for each instance
        of the entity (or module) or just once for all instances of the
        entity.
    """

    class Meta:
        name = "instanceGeneratorType"

    group: list[InstanceGeneratorType.Group] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    scope: InstanceGeneratorTypeScope = field(
        default=InstanceGeneratorTypeScope.INSTANCE,
        metadata={
            "type": "Attribute",
        },
    )

    @dataclass(kw_only=True)
    class Group:
        value: str = field(default="")
        id: None | str = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.w3.org/XML/1998/namespace",
            },
        )


@dataclass(kw_only=True)
class ServiceTypeDef:
    """
    Definition of a single service type defintion.

    :ivar type_name: The name of the service type. Can be any predefined
        type such as booean or integer or any user-defined type such as
        addr_type or data_type.
    :ivar type_definition: Where the definition of the type is contained
        if the type if not part of the language. For SystemC and
        SystemVerilog it is the include file containing the type
        definition.
    :ivar type_parameters:
    :ivar id:
    """

    class Meta:
        name = "serviceTypeDef"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    type_name: ServiceTypeDef.TypeName = field(
        metadata={
            "name": "typeName",
            "type": "Element",
        }
    )
    type_definition: list[ServiceTypeDef.TypeDefinition] = field(
        default_factory=list,
        metadata={
            "name": "typeDefinition",
            "type": "Element",
        },
    )
    type_parameters: None | TypeParameters = field(
        default=None,
        metadata={
            "name": "typeParameters",
            "type": "Element",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )

    @dataclass(kw_only=True)
    class TypeName:
        """
        :ivar value:
        :ivar implicit: Defines that the typeName supplied for this
            service is implicit and a netlister should not declare this
            service in a language specific top-level netlist
        """

        value: str = field(default="")
        implicit: bool = field(
            default=False,
            metadata={
                "type": "Attribute",
            },
        )

    @dataclass(kw_only=True)
    class TypeDefinition:
        value: str = field(default="")
        id: None | str = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.w3.org/XML/1998/namespace",
            },
        )


@dataclass(kw_only=True)
class TransTypeDef:
    """
    Definition of a single transactional type defintion.

    :ivar type_name: The name of the port type. Can be any predefined
        type such sc_port or sc_export in SystemC or any user-defined
        type such as tlm_port.
    :ivar type_definition: Where the definition of the type is
        contained. For SystemC and SystemVerilog it is the include file
        containing the type definition.
    :ivar type_parameters:
    :ivar view_ref: A reference to a view name in the file for which
        this type applies.
    :ivar id:
    """

    class Meta:
        name = "transTypeDef"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    type_name: None | TransTypeDef.TypeName = field(
        default=None,
        metadata={
            "name": "typeName",
            "type": "Element",
        },
    )
    type_definition: list[TransTypeDef.TypeDefinition] = field(
        default_factory=list,
        metadata={
            "name": "typeDefinition",
            "type": "Element",
        },
    )
    type_parameters: None | TypeParameters = field(
        default=None,
        metadata={
            "name": "typeParameters",
            "type": "Element",
        },
    )
    view_ref: list[TransTypeDef.ViewRef] = field(
        default_factory=list,
        metadata={
            "name": "viewRef",
            "type": "Element",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )

    @dataclass(kw_only=True)
    class TypeName:
        """
        :ivar value:
        :ivar exact: When false, defines that the type is an abstract
            type that may not be related to an existing type in the
            language of the referenced view.
        """

        value: str = field(default="")
        exact: bool = field(
            default=True,
            metadata={
                "type": "Attribute",
            },
        )

    @dataclass(kw_only=True)
    class TypeDefinition:
        value: str = field(default="")
        id: None | str = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.w3.org/XML/1998/namespace",
            },
        )

    @dataclass(kw_only=True)
    class ViewRef:
        value: str = field(default="")
        id: None | str = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.w3.org/XML/1998/namespace",
            },
        )


@dataclass(kw_only=True)
class AbstractorGenerator(InstanceGeneratorType):
    """
    Specifies a set of abstractor generators.

    The scope attribute applies to abstractor generators and specifies
    whether the generator should be run for each instance of the entity (or
    module) or just once for all instances of the entity.
    """

    class Meta:
        name = "abstractorGenerator"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"


@dataclass(kw_only=True)
class BusInterfaces:
    """
    A list of bus interfaces supported by this component.
    """

    class Meta:
        name = "busInterfaces"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    bus_interface: list[BusInterface] = field(
        default_factory=list,
        metadata={
            "name": "busInterface",
            "type": "Element",
            "min_occurs": 1,
        },
    )


@dataclass(kw_only=True)
class ComponentGenerator(InstanceGeneratorType):
    """
    Specifies a set of component generators.

    The scope attribute applies to component generators and specifies
    whether the generator should be run for each instance of the entity (or
    module) or just once for all instances of the entity.
    """

    class Meta:
        name = "componentGenerator"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"


@dataclass(kw_only=True)
class GeneratorChain:
    """
    :ivar vendor: Name of the vendor who supplies this file.
    :ivar library: Name of the logical library this element belongs to.
    :ivar name: The name of the object.
    :ivar version: Indicates the version of the named element.
    :ivar generator_chain_selector: Select other generator chain files
        for inclusion into this chain. The boolean attribute "unique"
        (default false) specifies that only a single generator is valid
        in this context. If more that one generator is selected based on
        the selection criteria, DE will prompt the user to resolve to a
        single generator.
    :ivar component_generator_selector: Selects generators declared in
        components of the current design for inclusion into this
        generator chain.
    :ivar generator:
    :ivar chain_group: Identifies this generator chain as belonging to
        the named group. This is used by other generator chains to
        select this chain for programmatic inclusion.
    :ivar display_name:
    :ivar description:
    :ivar choices:
    :ivar parameters:
    :ivar assertions:
    :ivar vendor_extensions:
    :ivar hidden: If this attribute is true then the generator should
        not be presented to the user, it may be part of a chain and has
        no useful meaning when invoked standalone.
    :ivar id:
    """

    class Meta:
        name = "generatorChain"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    vendor: str = field(
        metadata={
            "type": "Element",
        }
    )
    library: str = field(
        metadata={
            "type": "Element",
        }
    )
    name: str = field(
        metadata={
            "type": "Element",
        }
    )
    version: str = field(
        metadata={
            "type": "Element",
        }
    )
    generator_chain_selector: list[GeneratorChain.GeneratorChainSelector] = (
        field(
            default_factory=list,
            metadata={
                "name": "generatorChainSelector",
                "type": "Element",
            },
        )
    )
    component_generator_selector: list[GeneratorSelectorType] = field(
        default_factory=list,
        metadata={
            "name": "componentGeneratorSelector",
            "type": "Element",
        },
    )
    generator: list[Generator] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    chain_group: list[GeneratorChain.ChainGroup] = field(
        default_factory=list,
        metadata={
            "name": "chainGroup",
            "type": "Element",
        },
    )
    display_name: None | DisplayName = field(
        default=None,
        metadata={
            "name": "displayName",
            "type": "Element",
        },
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    choices: None | Choices = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    parameters: None | Parameters = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    assertions: None | Assertions = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
        },
    )
    hidden: bool = field(
        default=False,
        metadata={
            "type": "Attribute",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )

    @dataclass(kw_only=True)
    class ChainGroup:
        value: str = field(default="")
        id: None | str = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.w3.org/XML/1998/namespace",
            },
        )

    @dataclass(kw_only=True)
    class GeneratorChainSelector:
        """
        :ivar group_selector:
        :ivar generator_chain_ref: Select another generator chain using
            the unique identifier of this generator chain.
        :ivar unique: Specifies that only a single generator is valid in
            this context. If more that one generator is selcted based on
            the selection criteria, DE will prompt the user to resolve
            to a single generator.
        :ivar id:
        """

        group_selector: None | GroupSelector = field(
            default=None,
            metadata={
                "name": "groupSelector",
                "type": "Element",
            },
        )
        generator_chain_ref: None | ConfigurableLibraryRefType = field(
            default=None,
            metadata={
                "name": "generatorChainRef",
                "type": "Element",
            },
        )
        unique: bool = field(
            default=False,
            metadata={
                "type": "Attribute",
            },
        )
        id: None | str = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.w3.org/XML/1998/namespace",
            },
        )


@dataclass(kw_only=True)
class IndirectInterfaces:
    """
    A list of bus interfaces supported by this component.
    """

    class Meta:
        name = "indirectInterfaces"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    indirect_interface: list[IndirectInterface] = field(
        default_factory=list,
        metadata={
            "name": "indirectInterface",
            "type": "Element",
            "min_occurs": 1,
        },
    )


@dataclass(kw_only=True)
class RegisterFile:
    """
    A structure of registers and register files.

    :ivar name: Unique name
    :ivar display_name:
    :ivar description:
    :ivar access_handles:
    :ivar is_present:
    :ivar dim: Dimensions a register array, the semantics for dim
        elements are the same as the C language standard for the  layout
        of memory in multidimensional arrays.
    :ivar address_offset: Offset from the address block's baseAddress or
        the containing register file's addressOffset, expressed as the
        number of addressUnitBits from the containing memoryMap or
        localMemoryMap.
    :ivar type_identifier: Identifier name used to indicate that
        multiple registerFile elements contain the exact same
        information except for the elements in the
        registerFileInstanceGroup.
    :ivar range: The range of a register file.  Expressed as the number
        of addressable units accessible to the block. Specified in units
        of addressUnitBits.
    :ivar register: A single register
    :ivar register_file: A structure of registers and register files
    :ivar parameters:
    :ivar vendor_extensions:
    :ivar id:
    """

    class Meta:
        name = "registerFile"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    name: str = field(
        metadata={
            "type": "Element",
        }
    )
    display_name: None | DisplayName = field(
        default=None,
        metadata={
            "name": "displayName",
            "type": "Element",
        },
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    access_handles: None | RegisterFile.AccessHandles = field(
        default=None,
        metadata={
            "name": "accessHandles",
            "type": "Element",
        },
    )
    is_present: None | IsPresent = field(
        default=None,
        metadata={
            "name": "isPresent",
            "type": "Element",
        },
    )
    dim: list[RegisterFile.Dim] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    address_offset: UnsignedLongintExpression = field(
        metadata={
            "name": "addressOffset",
            "type": "Element",
        }
    )
    type_identifier: None | str = field(
        default=None,
        metadata={
            "name": "typeIdentifier",
            "type": "Element",
        },
    )
    range: UnsignedPositiveLongintExpression = field(
        metadata={
            "type": "Element",
        }
    )
    register: list[RegisterFile.Register] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    register_file: list[RegisterFile] = field(
        default_factory=list,
        metadata={
            "name": "registerFile",
            "type": "Element",
        },
    )
    parameters: None | Parameters = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )

    @dataclass(kw_only=True)
    class AccessHandles:
        access_handle: list[IndexedAccessHandle] = field(
            default_factory=list,
            metadata={
                "name": "accessHandle",
                "type": "Element",
                "min_occurs": 1,
            },
        )

    @dataclass(kw_only=True)
    class Dim(UnsignedLongintExpression):
        id: None | str = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.w3.org/XML/1998/namespace",
            },
        )

    @dataclass(kw_only=True)
    class Register:
        """
        :ivar name: Unique name
        :ivar display_name:
        :ivar description:
        :ivar access_handles:
        :ivar is_present:
        :ivar dim: Dimensions a register array, the semantics for dim
            elements are the same as the C language standard for the
            layout of memory in multidimensional arrays.
        :ivar address_offset: Offset from the address block's
            baseAddress or the containing register file's addressOffset,
            expressed as the number of addressUnitBits from the
            containing memoryMap or localMemoryMap.
        :ivar type_identifier: Identifier name used to indicate that
            multiple register elements contain the exact same
            information for the elements in the registerDefinitionGroup.
        :ivar size: Width of the register in bits.
        :ivar volatile:
        :ivar access:
        :ivar field_value: Describes individual bit fields within the
            register.
        :ivar alternate_registers:
        :ivar parameters:
        :ivar vendor_extensions:
        :ivar id:
        """

        name: str = field(
            metadata={
                "type": "Element",
            }
        )
        display_name: None | DisplayName = field(
            default=None,
            metadata={
                "name": "displayName",
                "type": "Element",
            },
        )
        description: None | Description = field(
            default=None,
            metadata={
                "type": "Element",
            },
        )
        access_handles: None | RegisterFile.Register.AccessHandles = field(
            default=None,
            metadata={
                "name": "accessHandles",
                "type": "Element",
            },
        )
        is_present: None | IsPresent = field(
            default=None,
            metadata={
                "name": "isPresent",
                "type": "Element",
            },
        )
        dim: list[RegisterFile.Register.Dim] = field(
            default_factory=list,
            metadata={
                "type": "Element",
            },
        )
        address_offset: UnsignedLongintExpression = field(
            metadata={
                "name": "addressOffset",
                "type": "Element",
            }
        )
        type_identifier: None | str = field(
            default=None,
            metadata={
                "name": "typeIdentifier",
                "type": "Element",
            },
        )
        size: UnsignedPositiveIntExpression = field(
            metadata={
                "type": "Element",
            }
        )
        volatile: None | Volatile = field(
            default=None,
            metadata={
                "type": "Element",
            },
        )
        access: None | Access = field(
            default=None,
            metadata={
                "type": "Element",
            },
        )
        field_value: list[FieldType] = field(
            default_factory=list,
            metadata={
                "name": "field",
                "type": "Element",
                "min_occurs": 1,
            },
        )
        alternate_registers: None | AlternateRegisters = field(
            default=None,
            metadata={
                "name": "alternateRegisters",
                "type": "Element",
            },
        )
        parameters: None | Parameters = field(
            default=None,
            metadata={
                "type": "Element",
            },
        )
        vendor_extensions: None | VendorExtensions = field(
            default=None,
            metadata={
                "name": "vendorExtensions",
                "type": "Element",
            },
        )
        id: None | str = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.w3.org/XML/1998/namespace",
            },
        )

        @dataclass(kw_only=True)
        class AccessHandles:
            access_handle: list[IndexedAccessHandle] = field(
                default_factory=list,
                metadata={
                    "name": "accessHandle",
                    "type": "Element",
                    "min_occurs": 1,
                },
            )

        @dataclass(kw_only=True)
        class Dim(UnsignedLongintExpression):
            id: None | str = field(
                default=None,
                metadata={
                    "type": "Attribute",
                    "namespace": "http://www.w3.org/XML/1998/namespace",
                },
            )


@dataclass(kw_only=True)
class ServiceTypeDefs:
    """
    The group of type definitions.

    If no match to a viewName is found then the default language types are
    to be used. See the User Guide for these default types.
    """

    class Meta:
        name = "serviceTypeDefs"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    service_type_def: list[ServiceTypeDef] = field(
        default_factory=list,
        metadata={
            "name": "serviceTypeDef",
            "type": "Element",
            "min_occurs": 1,
        },
    )


@dataclass(kw_only=True)
class TransTypeDefs:
    """
    The group of transactional type definitions.

    If no match to a viewName is found then the default language types are
    to be used. See the User Guide for these default types.
    """

    class Meta:
        name = "transTypeDefs"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    trans_type_def: list[TransTypeDef] = field(
        default_factory=list,
        metadata={
            "name": "transTypeDef",
            "type": "Element",
            "min_occurs": 1,
        },
    )


@dataclass(kw_only=True)
class AbstractorGenerators:
    """
    List of abstractor generators.
    """

    class Meta:
        name = "abstractorGenerators"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    abstractor_generator: list[AbstractorGenerator] = field(
        default_factory=list,
        metadata={
            "name": "abstractorGenerator",
            "type": "Element",
            "min_occurs": 1,
        },
    )


@dataclass(kw_only=True)
class AddressBlockType:
    """
    Top level address block that specify an address.

    :ivar name: Unique name
    :ivar display_name:
    :ivar description:
    :ivar access_handles:
    :ivar is_present:
    :ivar base_address:
    :ivar type_identifier: Identifier name used to indicate that
        multiple addressBlock elements contain the exact same
        information except for the elements in the
        addressBlockInstanceGroup.
    :ivar range: The address range of an address block.  Expressed as
        the number of addressable units accessible to the block. The
        range and the width are related by the following formulas:
        number_of_bits_in_block = ipxact:addressUnitBits * ipxact:range
        number_of_rows_in_block = number_of_bits_in_block / ipxact:width
    :ivar width: The bit width of a row in the address block. The range
        and the width are related by the following formulas:
        number_of_bits_in_block = ipxact:addressUnitBits * ipxact:range
        number_of_rows_in_block = number_of_bits_in_block / ipxact:width
    :ivar usage: Indicates the usage of this block.  Possible values are
        'memory', 'register' and 'reserved'.
    :ivar volatile:
    :ivar access:
    :ivar parameters: Any additional parameters needed to describe this
        address block to the generators.
    :ivar register: A single register
    :ivar register_file: A structure of registers and register files
    :ivar vendor_extensions:
    :ivar id:
    """

    class Meta:
        name = "addressBlockType"

    name: str = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    display_name: None | DisplayName = field(
        default=None,
        metadata={
            "name": "displayName",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    access_handles: None | AddressBlockType.AccessHandles = field(
        default=None,
        metadata={
            "name": "accessHandles",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    is_present: None | IsPresent = field(
        default=None,
        metadata={
            "name": "isPresent",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    base_address: BaseAddress = field(
        metadata={
            "name": "baseAddress",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    type_identifier: None | str = field(
        default=None,
        metadata={
            "name": "typeIdentifier",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    range: UnsignedPositiveLongintExpression = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    width: UnsignedIntExpression = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    usage: None | UsageType = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    volatile: None | Volatile = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    access: None | Access = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    parameters: None | Parameters = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    register: list[AddressBlockType.Register] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    register_file: list[RegisterFile] = field(
        default_factory=list,
        metadata={
            "name": "registerFile",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )

    @dataclass(kw_only=True)
    class AccessHandles:
        access_handle: list[NonIndexedLeafAccessHandle] = field(
            default_factory=list,
            metadata={
                "name": "accessHandle",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                "min_occurs": 1,
            },
        )

    @dataclass(kw_only=True)
    class Register:
        """
        :ivar name: Unique name
        :ivar display_name:
        :ivar description:
        :ivar access_handles:
        :ivar is_present:
        :ivar dim: Dimensions a register array, the semantics for dim
            elements are the same as the C language standard for the
            layout of memory in multidimensional arrays.
        :ivar address_offset: Offset from the address block's
            baseAddress or the containing register file's addressOffset,
            expressed as the number of addressUnitBits from the
            containing memoryMap or localMemoryMap.
        :ivar type_identifier: Identifier name used to indicate that
            multiple register elements contain the exact same
            information for the elements in the registerDefinitionGroup.
        :ivar size: Width of the register in bits.
        :ivar volatile:
        :ivar access:
        :ivar field_value: Describes individual bit fields within the
            register.
        :ivar alternate_registers:
        :ivar parameters:
        :ivar vendor_extensions:
        :ivar id:
        """

        name: str = field(
            metadata={
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            }
        )
        display_name: None | DisplayName = field(
            default=None,
            metadata={
                "name": "displayName",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            },
        )
        description: None | Description = field(
            default=None,
            metadata={
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            },
        )
        access_handles: None | AddressBlockType.Register.AccessHandles = field(
            default=None,
            metadata={
                "name": "accessHandles",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            },
        )
        is_present: None | IsPresent = field(
            default=None,
            metadata={
                "name": "isPresent",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            },
        )
        dim: list[AddressBlockType.Register.Dim] = field(
            default_factory=list,
            metadata={
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            },
        )
        address_offset: UnsignedLongintExpression = field(
            metadata={
                "name": "addressOffset",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            }
        )
        type_identifier: None | str = field(
            default=None,
            metadata={
                "name": "typeIdentifier",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            },
        )
        size: UnsignedPositiveIntExpression = field(
            metadata={
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            }
        )
        volatile: None | Volatile = field(
            default=None,
            metadata={
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            },
        )
        access: None | Access = field(
            default=None,
            metadata={
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            },
        )
        field_value: list[FieldType] = field(
            default_factory=list,
            metadata={
                "name": "field",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                "min_occurs": 1,
            },
        )
        alternate_registers: None | AlternateRegisters = field(
            default=None,
            metadata={
                "name": "alternateRegisters",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            },
        )
        parameters: None | Parameters = field(
            default=None,
            metadata={
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            },
        )
        vendor_extensions: None | VendorExtensions = field(
            default=None,
            metadata={
                "name": "vendorExtensions",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            },
        )
        id: None | str = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.w3.org/XML/1998/namespace",
            },
        )

        @dataclass(kw_only=True)
        class AccessHandles:
            access_handle: list[IndexedAccessHandle] = field(
                default_factory=list,
                metadata={
                    "name": "accessHandle",
                    "type": "Element",
                    "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                    "min_occurs": 1,
                },
            )

        @dataclass(kw_only=True)
        class Dim(UnsignedLongintExpression):
            id: None | str = field(
                default=None,
                metadata={
                    "type": "Attribute",
                    "namespace": "http://www.w3.org/XML/1998/namespace",
                },
            )


@dataclass(kw_only=True)
class BankedBlockType:
    """
    Address blocks inside a bank do not specify address.

    :ivar name: Unique name
    :ivar display_name:
    :ivar description:
    :ivar access_handles:
    :ivar is_present:
    :ivar range: The address range of an address block.  Expressed as
        the number of addressable units accessible to the block. The
        range and the width are related by the following formulas:
        number_of_bits_in_block = ipxact:addressUnitBits * ipxact:range
        number_of_rows_in_block = number_of_bits_in_block / ipxact:width
    :ivar width: The bit width of a row in the address block. The range
        and the width are related by the following formulas:
        number_of_bits_in_block = ipxact:addressUnitBits * ipxact:range
        number_of_rows_in_block = number_of_bits_in_block / ipxact:width
    :ivar usage: Indicates the usage of this block.  Possible values are
        'memory', 'register' and 'reserved'.
    :ivar volatile:
    :ivar access:
    :ivar parameters: Any additional parameters needed to describe this
        address block to the generators.
    :ivar register: A single register
    :ivar register_file: A structure of registers and register files
    :ivar vendor_extensions:
    :ivar id:
    """

    class Meta:
        name = "bankedBlockType"

    name: str = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    display_name: None | DisplayName = field(
        default=None,
        metadata={
            "name": "displayName",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    access_handles: None | BankedBlockType.AccessHandles = field(
        default=None,
        metadata={
            "name": "accessHandles",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    is_present: None | IsPresent = field(
        default=None,
        metadata={
            "name": "isPresent",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    range: UnsignedPositiveLongintExpression = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    width: UnsignedIntExpression = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    usage: None | UsageType = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    volatile: None | Volatile = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    access: None | Access = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    parameters: None | Parameters = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    register: list[BankedBlockType.Register] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    register_file: list[RegisterFile] = field(
        default_factory=list,
        metadata={
            "name": "registerFile",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )

    @dataclass(kw_only=True)
    class AccessHandles:
        access_handle: list[NonIndexedLeafAccessHandle] = field(
            default_factory=list,
            metadata={
                "name": "accessHandle",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                "min_occurs": 1,
            },
        )

    @dataclass(kw_only=True)
    class Register:
        """
        :ivar name: Unique name
        :ivar display_name:
        :ivar description:
        :ivar access_handles:
        :ivar is_present:
        :ivar dim: Dimensions a register array, the semantics for dim
            elements are the same as the C language standard for the
            layout of memory in multidimensional arrays.
        :ivar address_offset: Offset from the address block's
            baseAddress or the containing register file's addressOffset,
            expressed as the number of addressUnitBits from the
            containing memoryMap or localMemoryMap.
        :ivar type_identifier: Identifier name used to indicate that
            multiple register elements contain the exact same
            information for the elements in the registerDefinitionGroup.
        :ivar size: Width of the register in bits.
        :ivar volatile:
        :ivar access:
        :ivar field_value: Describes individual bit fields within the
            register.
        :ivar alternate_registers:
        :ivar parameters:
        :ivar vendor_extensions:
        :ivar id:
        """

        name: str = field(
            metadata={
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            }
        )
        display_name: None | DisplayName = field(
            default=None,
            metadata={
                "name": "displayName",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            },
        )
        description: None | Description = field(
            default=None,
            metadata={
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            },
        )
        access_handles: None | BankedBlockType.Register.AccessHandles = field(
            default=None,
            metadata={
                "name": "accessHandles",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            },
        )
        is_present: None | IsPresent = field(
            default=None,
            metadata={
                "name": "isPresent",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            },
        )
        dim: list[BankedBlockType.Register.Dim] = field(
            default_factory=list,
            metadata={
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            },
        )
        address_offset: UnsignedLongintExpression = field(
            metadata={
                "name": "addressOffset",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            }
        )
        type_identifier: None | str = field(
            default=None,
            metadata={
                "name": "typeIdentifier",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            },
        )
        size: UnsignedPositiveIntExpression = field(
            metadata={
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            }
        )
        volatile: None | Volatile = field(
            default=None,
            metadata={
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            },
        )
        access: None | Access = field(
            default=None,
            metadata={
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            },
        )
        field_value: list[FieldType] = field(
            default_factory=list,
            metadata={
                "name": "field",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                "min_occurs": 1,
            },
        )
        alternate_registers: None | AlternateRegisters = field(
            default=None,
            metadata={
                "name": "alternateRegisters",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            },
        )
        parameters: None | Parameters = field(
            default=None,
            metadata={
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            },
        )
        vendor_extensions: None | VendorExtensions = field(
            default=None,
            metadata={
                "name": "vendorExtensions",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            },
        )
        id: None | str = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.w3.org/XML/1998/namespace",
            },
        )

        @dataclass(kw_only=True)
        class AccessHandles:
            access_handle: list[IndexedAccessHandle] = field(
                default_factory=list,
                metadata={
                    "name": "accessHandle",
                    "type": "Element",
                    "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                    "min_occurs": 1,
                },
            )

        @dataclass(kw_only=True)
        class Dim(UnsignedLongintExpression):
            id: None | str = field(
                default=None,
                metadata={
                    "type": "Attribute",
                    "namespace": "http://www.w3.org/XML/1998/namespace",
                },
            )


@dataclass(kw_only=True)
class ComponentGenerators:
    """
    List of component generators.
    """

    class Meta:
        name = "componentGenerators"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    component_generator: list[ComponentGenerator] = field(
        default_factory=list,
        metadata={
            "name": "componentGenerator",
            "type": "Element",
            "min_occurs": 1,
        },
    )


@dataclass(kw_only=True)
class PortTransactionalType:
    """
    Transactional port type.

    :ivar initiative: Defines how the port accesses this service.
    :ivar kind: Define the kind of transactional port
    :ivar bus_width: Defines the bus width in bits.This can be the
        result of an expression.
    :ivar protocol: Defines the protocol type. Defaults to
        tlm_base_protocol_type for TLM sockets
    :ivar trans_type_defs: Definition of the port type expressed in the
        default language for this port (i.e. SystemC or SystemV).
    :ivar connection: Bounds number of legal connections.
    :ivar all_logical_initiatives_allowed: True if logical ports with
        different initiatives from the physical port initiative may be
        mapped onto this port. Forbidden for phantom ports, which always
        allow logical ports with all initiatives value to be mapped onto
        the physical port. Also ignored for "both" ports, since any
        logical port may be mapped to a physical "both" port.
    """

    class Meta:
        name = "portTransactionalType"

    initiative: Initiative = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    kind: None | Kind = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    bus_width: None | BusWidth = field(
        default=None,
        metadata={
            "name": "busWidth",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    protocol: None | Protocol = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    trans_type_defs: None | TransTypeDefs = field(
        default=None,
        metadata={
            "name": "transTypeDefs",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    connection: None | PortTransactionalType.Connection = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    all_logical_initiatives_allowed: bool = field(
        default=False,
        metadata={
            "name": "allLogicalInitiativesAllowed",
            "type": "Attribute",
        },
    )

    @dataclass(kw_only=True)
    class Connection:
        """
        :ivar max_connections: Indicates the maximum number of
            connections this port supports. If this element is not
            present or set to 0 it implies an unbounded number of
            allowed connections.
        :ivar min_connections: Indicates the minimum number of
            connections this port supports. If this element is not
            present, the minimum number of allowed connections is 1.
        """

        max_connections: None | UnsignedIntExpression = field(
            default=None,
            metadata={
                "name": "maxConnections",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            },
        )
        min_connections: None | UnsignedIntExpression = field(
            default=None,
            metadata={
                "name": "minConnections",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            },
        )


@dataclass(kw_only=True)
class AddressBlock(AddressBlockType):
    """
    This is a single contiguous block of memory inside a memory map.
    """

    class Meta:
        name = "addressBlock"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"


@dataclass(kw_only=True)
class BankedBankType:
    """
    Banks nested inside a bank do not specify address.

    :ivar name: Unique name
    :ivar display_name:
    :ivar description:
    :ivar access_handles:
    :ivar is_present:
    :ivar address_block: An address block within the bank.  No address
        information is supplied.
    :ivar bank: A nested bank of blocks within a bank.  No address
        information is supplied.
    :ivar subspace_map: A subspace map within the bank.  No address
        information is supplied.
    :ivar usage: Indicates the usage of this block.  Possible values are
        'memory', 'register' and 'reserved'.
    :ivar volatile:
    :ivar access:
    :ivar parameters: Any additional parameters needed to describe this
        address block to the generators.
    :ivar vendor_extensions:
    :ivar bank_alignment:
    :ivar id:
    """

    class Meta:
        name = "bankedBankType"

    name: str = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    display_name: None | DisplayName = field(
        default=None,
        metadata={
            "name": "displayName",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    access_handles: None | BankedBankType.AccessHandles = field(
        default=None,
        metadata={
            "name": "accessHandles",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    is_present: None | IsPresent = field(
        default=None,
        metadata={
            "name": "isPresent",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    address_block: list[BankedBlockType] = field(
        default_factory=list,
        metadata={
            "name": "addressBlock",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    bank: list[BankedBankType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    subspace_map: list[BankedSubspaceType] = field(
        default_factory=list,
        metadata={
            "name": "subspaceMap",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    usage: None | UsageType = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    volatile: None | Volatile = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    access: None | Access = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    parameters: None | Parameters = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    bank_alignment: BankAlignmentType = field(
        metadata={
            "name": "bankAlignment",
            "type": "Attribute",
        }
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )

    @dataclass(kw_only=True)
    class AccessHandles:
        access_handle: list[SimpleAccessHandle] = field(
            default_factory=list,
            metadata={
                "name": "accessHandle",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                "min_occurs": 1,
            },
        )


@dataclass(kw_only=True)
class LocalBankedBankType:
    """
    Banks nested inside a bank do not specify address.

    :ivar name: Unique name
    :ivar display_name:
    :ivar description:
    :ivar access_handles:
    :ivar is_present:
    :ivar address_block: An address block within the bank.  No address
        information is supplied.
    :ivar bank: A nested bank of blocks within a bank.  No address
        information is supplied.
    :ivar usage: Indicates the usage of this block.  Possible values are
        'memory', 'register' and 'reserved'.
    :ivar volatile:
    :ivar access:
    :ivar parameters: Any additional parameters needed to describe this
        address block to the generators.
    :ivar vendor_extensions:
    :ivar bank_alignment:
    :ivar id:
    """

    class Meta:
        name = "localBankedBankType"

    name: str = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    display_name: None | DisplayName = field(
        default=None,
        metadata={
            "name": "displayName",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    access_handles: None | LocalBankedBankType.AccessHandles = field(
        default=None,
        metadata={
            "name": "accessHandles",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    is_present: None | IsPresent = field(
        default=None,
        metadata={
            "name": "isPresent",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    address_block: list[BankedBlockType] = field(
        default_factory=list,
        metadata={
            "name": "addressBlock",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    bank: list[LocalBankedBankType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    usage: None | UsageType = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    volatile: None | Volatile = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    access: None | Access = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    parameters: None | Parameters = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    bank_alignment: BankAlignmentType = field(
        metadata={
            "name": "bankAlignment",
            "type": "Attribute",
        }
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )

    @dataclass(kw_only=True)
    class AccessHandles:
        access_handle: list[SimpleAccessHandle] = field(
            default_factory=list,
            metadata={
                "name": "accessHandle",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                "min_occurs": 1,
            },
        )


@dataclass(kw_only=True)
class PortType:
    """
    A port description, giving a name and an access type for high level
    ports.

    :ivar name: Unique name
    :ivar display_name:
    :ivar description:
    :ivar is_present:
    :ivar wire: Defines a port whose type resolves to simple bits.
    :ivar transactional: Defines a port that implements or uses a
        service that can be implemented with functions or methods.
    :ivar arrays:
    :ivar access: Port access characteristics.
    :ivar vendor_extensions:
    :ivar id:
    """

    class Meta:
        name = "portType"

    name: str = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            "white_space": "collapse",
            "pattern": r"\i[\p{L}\p{N}\.\-:_]*",
        }
    )
    display_name: None | DisplayName = field(
        default=None,
        metadata={
            "name": "displayName",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    is_present: None | IsPresent = field(
        default=None,
        metadata={
            "name": "isPresent",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    wire: None | PortWireType = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    transactional: None | PortTransactionalType = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    arrays: None | Arrays = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    access: None | PortAccessType1 = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )


@dataclass(kw_only=True)
class AbstractorPortType(PortType):
    """
    A port description, giving a name and an access type for high level
    ports.
    """

    class Meta:
        name = "abstractorPortType"

    arrays: Any = field(
        init=False,
        default=None,
        metadata={
            "type": "Ignore",
        },
    )


@dataclass(kw_only=True)
class AddressBankType:
    """
    Top level bank the specify an address.

    :ivar name: Unique name
    :ivar display_name:
    :ivar description:
    :ivar access_handles:
    :ivar base_address:
    :ivar is_present:
    :ivar address_block: An address block within the bank.  No address
        information is supplied.
    :ivar bank: A nested bank of blocks within a bank.  No address
        information is supplied.
    :ivar subspace_map: A subspace map within the bank.  No address
        information is supplied.
    :ivar usage: Indicates the usage of this block.  Possible values are
        'memory', 'register' and 'reserved'.
    :ivar volatile:
    :ivar access:
    :ivar parameters: Any additional parameters needed to describe this
        address block to the generators.
    :ivar vendor_extensions:
    :ivar bank_alignment: Describes whether this bank's blocks are
        aligned in 'parallel' or 'serial'.
    :ivar id:
    """

    class Meta:
        name = "addressBankType"

    name: str = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    display_name: None | DisplayName = field(
        default=None,
        metadata={
            "name": "displayName",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    access_handles: None | AddressBankType.AccessHandles = field(
        default=None,
        metadata={
            "name": "accessHandles",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    base_address: BaseAddress = field(
        metadata={
            "name": "baseAddress",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    is_present: None | IsPresent = field(
        default=None,
        metadata={
            "name": "isPresent",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    address_block: list[BankedBlockType] = field(
        default_factory=list,
        metadata={
            "name": "addressBlock",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    bank: list[BankedBankType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    subspace_map: list[BankedSubspaceType] = field(
        default_factory=list,
        metadata={
            "name": "subspaceMap",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    usage: None | UsageType = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    volatile: None | Volatile = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    access: None | Access = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    parameters: None | Parameters = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    bank_alignment: BankAlignmentType = field(
        metadata={
            "name": "bankAlignment",
            "type": "Attribute",
        }
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )

    @dataclass(kw_only=True)
    class AccessHandles:
        access_handle: list[SimpleAccessHandle] = field(
            default_factory=list,
            metadata={
                "name": "accessHandle",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                "min_occurs": 1,
            },
        )


@dataclass(kw_only=True)
class LocalAddressBankType:
    """
    Top level bank the specify an address.

    :ivar name: Unique name
    :ivar display_name:
    :ivar description:
    :ivar access_handles:
    :ivar base_address:
    :ivar is_present:
    :ivar address_block: An address block within the bank.  No address
        information is supplied.
    :ivar bank: A nested bank of blocks within a bank.  No address
        information is supplied.
    :ivar usage: Indicates the usage of this block.  Possible values are
        'memory', 'register' and 'reserved'.
    :ivar volatile:
    :ivar access:
    :ivar parameters: Any additional parameters needed to describe this
        address block to the generators.
    :ivar vendor_extensions:
    :ivar bank_alignment: Describes whether this bank's blocks are
        aligned in 'parallel' or 'serial'.
    :ivar id:
    """

    class Meta:
        name = "localAddressBankType"

    name: str = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    display_name: None | DisplayName = field(
        default=None,
        metadata={
            "name": "displayName",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    access_handles: None | LocalAddressBankType.AccessHandles = field(
        default=None,
        metadata={
            "name": "accessHandles",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    base_address: BaseAddress = field(
        metadata={
            "name": "baseAddress",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    is_present: None | IsPresent = field(
        default=None,
        metadata={
            "name": "isPresent",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    address_block: list[BankedBlockType] = field(
        default_factory=list,
        metadata={
            "name": "addressBlock",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    bank: list[LocalBankedBankType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    usage: None | UsageType = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    volatile: None | Volatile = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    access: None | Access = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    parameters: None | Parameters = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    bank_alignment: BankAlignmentType = field(
        metadata={
            "name": "bankAlignment",
            "type": "Attribute",
        }
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )

    @dataclass(kw_only=True)
    class AccessHandles:
        access_handle: list[SimpleAccessHandle] = field(
            default_factory=list,
            metadata={
                "name": "accessHandle",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                "min_occurs": 1,
            },
        )


@dataclass(kw_only=True)
class Port(PortType):
    """
    Describes port characteristics.
    """

    class Meta:
        name = "port"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"


@dataclass(kw_only=True)
class AbstractorModelType:
    """
    Model information for an abstractor.

    :ivar views: Views container
    :ivar instantiations: Instantiations container
    :ivar ports: Port container
    """

    class Meta:
        name = "abstractorModelType"

    views: None | AbstractorModelType.Views = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    instantiations: None | AbstractorModelType.Instantiations = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    ports: None | AbstractorModelType.Ports = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )

    @dataclass(kw_only=True)
    class Views:
        """
        :ivar view: Single view of an abstracto
        """

        view: list[AbstractorModelType.Views.View] = field(
            default_factory=list,
            metadata={
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                "min_occurs": 1,
            },
        )

        @dataclass(kw_only=True)
        class View:
            """
            :ivar name: Unique name
            :ivar display_name:
            :ivar description:
            :ivar is_present:
            :ivar env_identifier: Defines the hardware environment in
                which this view applies. The format of the string is
                language:tool:vendor_extension, with each piece being
                optional. The language must be one of the types from
                ipxact:fileType. The tool values are defined by the
                Accellera Systems Initiative, and include generic values
                "*Simulation" and "*Synthesis" to imply any tool of the
                indicated type. Having more than one envIdentifier
                indicates that the view applies to multiple
                environments.
            :ivar component_instantiation_ref:
            """

            name: str = field(
                metadata={
                    "type": "Element",
                    "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                }
            )
            display_name: None | DisplayName = field(
                default=None,
                metadata={
                    "name": "displayName",
                    "type": "Element",
                    "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                },
            )
            description: None | Description = field(
                default=None,
                metadata={
                    "type": "Element",
                    "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                },
            )
            is_present: None | IsPresent = field(
                default=None,
                metadata={
                    "name": "isPresent",
                    "type": "Element",
                    "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                },
            )
            env_identifier: list[
                AbstractorModelType.Views.View.EnvIdentifier
            ] = field(
                default_factory=list,
                metadata={
                    "name": "envIdentifier",
                    "type": "Element",
                    "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                },
            )
            component_instantiation_ref: None | str = field(
                default=None,
                metadata={
                    "name": "componentInstantiationRef",
                    "type": "Element",
                    "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                },
            )

            @dataclass(kw_only=True)
            class EnvIdentifier:
                value: str = field(
                    default="",
                    metadata={
                        "pattern": r"[a-zA-Z0-9_+\*\.]*:[a-zA-Z0-9_+\*\.]*:[a-zA-Z0-9_+\*\.]*",
                    },
                )
                id: None | str = field(
                    default=None,
                    metadata={
                        "type": "Attribute",
                        "namespace": "http://www.w3.org/XML/1998/namespace",
                    },
                )

    @dataclass(kw_only=True)
    class Instantiations:
        """
        :ivar component_instantiation: Component Instantiation
        """

        component_instantiation: list[ComponentInstantiationType] = field(
            default_factory=list,
            metadata={
                "name": "componentInstantiation",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                "min_occurs": 1,
            },
        )

    @dataclass(kw_only=True)
    class Ports:
        port: list[AbstractorPortType] = field(
            default_factory=list,
            metadata={
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            },
        )


@dataclass(kw_only=True)
class Bank(AddressBankType):
    """
    Represents a bank of memory made up of address blocks or other banks.

    It has a bankAlignment attribute indicating whether its blocks are
    aligned in 'parallel' (occupying adjacent bit fields) or 'serial'
    (occupying contiguous addresses). Its child blocks do not contain
    addresses or bit offsets.
    """

    class Meta:
        name = "bank"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"


@dataclass(kw_only=True)
class LocalMemoryMapType:
    """
    Map of address space blocks on the local memory map of a master bus
    interface.

    :ivar name: Unique name
    :ivar display_name:
    :ivar description:
    :ivar is_present:
    :ivar address_block:
    :ivar bank: Represents a bank of memory made up of address blocks or
        other banks.  It has a bankAlignment attribute indicating
        whether its blocks are aligned in 'parallel' (occupying adjacent
        bit fields) or 'serial' (occupying contiguous addresses). Its
        child blocks do not contain addresses or bit offsets.
    :ivar id:
    """

    class Meta:
        name = "localMemoryMapType"

    name: str = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    display_name: None | DisplayName = field(
        default=None,
        metadata={
            "name": "displayName",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    is_present: None | IsPresent = field(
        default=None,
        metadata={
            "name": "isPresent",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    address_block: list[AddressBlock] = field(
        default_factory=list,
        metadata={
            "name": "addressBlock",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    bank: list[LocalAddressBankType] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )


@dataclass(kw_only=True)
class ModelType:
    """
    Model information.

    :ivar views: Views container
    :ivar instantiations: Instantiations container
    :ivar ports: Port container
    """

    class Meta:
        name = "modelType"

    views: None | ModelType.Views = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    instantiations: None | ModelType.Instantiations = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    ports: None | ModelType.Ports = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )

    @dataclass(kw_only=True)
    class Views:
        """
        :ivar view: Single view of a component
        """

        view: list[ModelType.Views.View] = field(
            default_factory=list,
            metadata={
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                "min_occurs": 1,
            },
        )

        @dataclass(kw_only=True)
        class View:
            """
            :ivar name: Unique name
            :ivar display_name:
            :ivar description:
            :ivar is_present:
            :ivar env_identifier: Defines the hardware environment in
                which this view applies. The format of the string is
                language:tool:vendor_extension, with each piece being
                optional. The language must be one of the types from
                ipxact:fileType. The tool values are defined by the
                Accellera Systems Initiative, and include generic values
                "*Simulation" and "*Synthesis" to imply any tool of the
                indicated type. Having more than one envIdentifier
                indicates that the view applies to multiple
                environments.
            :ivar component_instantiation_ref:
            :ivar design_instantiation_ref:
            :ivar design_configuration_instantiation_ref:
            """

            name: str = field(
                metadata={
                    "type": "Element",
                    "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                }
            )
            display_name: None | DisplayName = field(
                default=None,
                metadata={
                    "name": "displayName",
                    "type": "Element",
                    "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                },
            )
            description: None | Description = field(
                default=None,
                metadata={
                    "type": "Element",
                    "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                },
            )
            is_present: None | IsPresent = field(
                default=None,
                metadata={
                    "name": "isPresent",
                    "type": "Element",
                    "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                },
            )
            env_identifier: list[ModelType.Views.View.EnvIdentifier] = field(
                default_factory=list,
                metadata={
                    "name": "envIdentifier",
                    "type": "Element",
                    "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                },
            )
            component_instantiation_ref: None | str = field(
                default=None,
                metadata={
                    "name": "componentInstantiationRef",
                    "type": "Element",
                    "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                },
            )
            design_instantiation_ref: None | str = field(
                default=None,
                metadata={
                    "name": "designInstantiationRef",
                    "type": "Element",
                    "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                },
            )
            design_configuration_instantiation_ref: None | str = field(
                default=None,
                metadata={
                    "name": "designConfigurationInstantiationRef",
                    "type": "Element",
                    "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                },
            )

            @dataclass(kw_only=True)
            class EnvIdentifier:
                value: str = field(
                    default="",
                    metadata={
                        "pattern": r"[a-zA-Z0-9_+\*\.]*:[a-zA-Z0-9_+\*\.]*:[a-zA-Z0-9_+\*\.]*",
                    },
                )
                id: None | str = field(
                    default=None,
                    metadata={
                        "type": "Attribute",
                        "namespace": "http://www.w3.org/XML/1998/namespace",
                    },
                )

    @dataclass(kw_only=True)
    class Instantiations:
        """
        :ivar component_instantiation: Component Instantiation
        :ivar design_instantiation: Design Instantiation
        :ivar design_configuration_instantiation: Design Configuration
            Instantiation
        """

        component_instantiation: list[ComponentInstantiationType] = field(
            default_factory=list,
            metadata={
                "name": "componentInstantiation",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            },
        )
        design_instantiation: list[DesignInstantiationType] = field(
            default_factory=list,
            metadata={
                "name": "designInstantiation",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            },
        )
        design_configuration_instantiation: list[
            DesignConfigurationInstantiationType
        ] = field(
            default_factory=list,
            metadata={
                "name": "designConfigurationInstantiation",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
            },
        )

    @dataclass(kw_only=True)
    class Ports:
        port: list[Port] = field(
            default_factory=list,
            metadata={
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                "min_occurs": 1,
            },
        )


@dataclass(kw_only=True)
class AbstractorType:
    """
    Abstractor-specific extension to abstractorType.

    :ivar vendor: Name of the vendor who supplies this file.
    :ivar library: Name of the logical library this element belongs to.
    :ivar name: The name of the object.
    :ivar version: Indicates the version of the named element.
    :ivar abstractor_mode: Define the mode for the interfaces on this
        abstractor. For master the first interface connects to the
        master, the second connects to the mirroredMaster For slave the
        first interface connects to the mirroredSlave the second
        connects to the slave For direct the first interface connects to
        the master, the second connects to the slave For system the
        first interface connects to the system, the second connects to
        the mirroredSystem. For system the group attribute is required
    :ivar bus_type: The bus type of both interfaces. Refers to bus
        definition using vendor, library, name, version attributes.
    :ivar abstractor_interfaces: The interfaces supported by this
        abstractor
    :ivar model: Model information.
    :ivar abstractor_generators: Generator list is tools-specific.
    :ivar choices:
    :ivar file_sets:
    :ivar description:
    :ivar parameters:
    :ivar assertions:
    :ivar vendor_extensions:
    :ivar id:
    """

    class Meta:
        name = "abstractorType"

    vendor: str = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    library: str = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    name: str = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    version: str = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    abstractor_mode: AbstractorType.AbstractorMode = field(
        metadata={
            "name": "abstractorMode",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    bus_type: LibraryRefType = field(
        metadata={
            "name": "busType",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    abstractor_interfaces: AbstractorType.AbstractorInterfaces = field(
        metadata={
            "name": "abstractorInterfaces",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    model: None | AbstractorModelType = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    abstractor_generators: None | AbstractorGenerators = field(
        default=None,
        metadata={
            "name": "abstractorGenerators",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    choices: None | Choices = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    file_sets: None | FileSets = field(
        default=None,
        metadata={
            "name": "fileSets",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    parameters: None | Parameters = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    assertions: None | Assertions = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )

    @dataclass(kw_only=True)
    class AbstractorMode:
        """
        :ivar value:
        :ivar group: Define the system group if the mode is set to
            system
        """

        value: AbstractorModeType = field()
        group: None | str = field(
            default=None,
            metadata={
                "type": "Attribute",
            },
        )

    @dataclass(kw_only=True)
    class AbstractorInterfaces:
        """
        :ivar abstractor_interface: An abstractor must have exactly 2
            Interfaces.
        """

        abstractor_interface: list[AbstractorBusInterfaceType] = field(
            default_factory=list,
            metadata={
                "name": "abstractorInterface",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                "min_occurs": 2,
                "max_occurs": 2,
            },
        )


@dataclass(kw_only=True)
class AddressSpaces:
    """
    If this component is a bus master, this lists all the address spaces
    defined by the component.

    :ivar address_space: This defines a logical space, referenced by a
        bus master.
    """

    class Meta:
        name = "addressSpaces"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    address_space: list[AddressSpaces.AddressSpace] = field(
        default_factory=list,
        metadata={
            "name": "addressSpace",
            "type": "Element",
            "min_occurs": 1,
        },
    )

    @dataclass(kw_only=True)
    class AddressSpace:
        """
        :ivar name: Unique name
        :ivar display_name:
        :ivar description:
        :ivar is_present:
        :ivar range: The address range of an address block.  Expressed
            as the number of addressable units accessible to the block.
            The range and the width are related by the following
            formulas: number_of_bits_in_block = ipxact:addressUnitBits *
            ipxact:range number_of_rows_in_block =
            number_of_bits_in_block / ipxact:width
        :ivar width: The bit width of a row in the address block. The
            range and the width are related by the following formulas:
            number_of_bits_in_block = ipxact:addressUnitBits *
            ipxact:range number_of_rows_in_block =
            number_of_bits_in_block / ipxact:width
        :ivar segments: Address segments withing an addressSpace
        :ivar address_unit_bits:
        :ivar executable_image:
        :ivar local_memory_map: Provides the local memory map of an
            address space.  Blocks in this memory map are accessable to
            master interfaces on this component that reference this
            address space.   They are not accessable to any external
            master interface.
        :ivar parameters: Data specific to this address space.
        :ivar vendor_extensions:
        :ivar id:
        """

        name: str = field(
            metadata={
                "type": "Element",
            }
        )
        display_name: None | DisplayName = field(
            default=None,
            metadata={
                "name": "displayName",
                "type": "Element",
            },
        )
        description: None | Description = field(
            default=None,
            metadata={
                "type": "Element",
            },
        )
        is_present: None | IsPresent = field(
            default=None,
            metadata={
                "name": "isPresent",
                "type": "Element",
            },
        )
        range: UnsignedPositiveLongintExpression = field(
            metadata={
                "type": "Element",
            }
        )
        width: UnsignedIntExpression = field(
            metadata={
                "type": "Element",
            }
        )
        segments: None | AddressSpaces.AddressSpace.Segments = field(
            default=None,
            metadata={
                "type": "Element",
            },
        )
        address_unit_bits: None | AddressUnitBits = field(
            default=None,
            metadata={
                "name": "addressUnitBits",
                "type": "Element",
            },
        )
        executable_image: list[ExecutableImage] = field(
            default_factory=list,
            metadata={
                "name": "executableImage",
                "type": "Element",
            },
        )
        local_memory_map: None | LocalMemoryMapType = field(
            default=None,
            metadata={
                "name": "localMemoryMap",
                "type": "Element",
            },
        )
        parameters: None | Parameters = field(
            default=None,
            metadata={
                "type": "Element",
            },
        )
        vendor_extensions: None | VendorExtensions = field(
            default=None,
            metadata={
                "name": "vendorExtensions",
                "type": "Element",
            },
        )
        id: None | str = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.w3.org/XML/1998/namespace",
            },
        )

        @dataclass(kw_only=True)
        class Segments:
            """
            :ivar segment: Address segment withing an addressSpace
            """

            segment: list[AddressSpaces.AddressSpace.Segments.Segment] = field(
                default_factory=list,
                metadata={
                    "type": "Element",
                    "min_occurs": 1,
                },
            )

            @dataclass(kw_only=True)
            class Segment:
                """
                :ivar name: Unique name
                :ivar display_name:
                :ivar description:
                :ivar is_present:
                :ivar address_offset: Address offset of the segment
                    within the containing address space.
                :ivar range: The address range of asegment.  Expressed
                    as the number of addressable units accessible to the
                    segment.
                :ivar vendor_extensions:
                :ivar id:
                """

                name: str = field(
                    metadata={
                        "type": "Element",
                    }
                )
                display_name: None | DisplayName = field(
                    default=None,
                    metadata={
                        "name": "displayName",
                        "type": "Element",
                    },
                )
                description: None | Description = field(
                    default=None,
                    metadata={
                        "type": "Element",
                    },
                )
                is_present: None | IsPresent = field(
                    default=None,
                    metadata={
                        "name": "isPresent",
                        "type": "Element",
                    },
                )
                address_offset: UnsignedLongintExpression = field(
                    metadata={
                        "name": "addressOffset",
                        "type": "Element",
                    }
                )
                range: UnsignedPositiveLongintExpression = field(
                    metadata={
                        "type": "Element",
                    }
                )
                vendor_extensions: None | VendorExtensions = field(
                    default=None,
                    metadata={
                        "name": "vendorExtensions",
                        "type": "Element",
                    },
                )
                id: None | str = field(
                    default=None,
                    metadata={
                        "type": "Attribute",
                        "namespace": "http://www.w3.org/XML/1998/namespace",
                    },
                )


@dataclass(kw_only=True)
class MemoryRemapType:
    """
    Map of address space blocks on a slave bus interface in a specific
    remap state.

    :ivar name: Unique name
    :ivar display_name:
    :ivar description:
    :ivar is_present:
    :ivar address_block:
    :ivar bank:
    :ivar subspace_map: Maps in an address subspace from across a bus
        bridge.  Its masterRef attribute refers by name to the master
        bus interface on the other side of the bridge.  It must match
        the masterRef attribute of a bridge element on the slave
        interface, and that bridge element must be designated as opaque.
    :ivar state: State of the component in which the memory map is
        active.
    :ivar id:
    """

    class Meta:
        name = "memoryRemapType"

    name: str = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    display_name: None | DisplayName = field(
        default=None,
        metadata={
            "name": "displayName",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    is_present: None | IsPresent = field(
        default=None,
        metadata={
            "name": "isPresent",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    address_block: list[AddressBlock] = field(
        default_factory=list,
        metadata={
            "name": "addressBlock",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    bank: list[Bank] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    subspace_map: list[SubspaceRefType] = field(
        default_factory=list,
        metadata={
            "name": "subspaceMap",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    state: str = field(
        metadata={
            "type": "Attribute",
        }
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )


@dataclass(kw_only=True)
class Model(ModelType):
    """
    Model information.
    """

    class Meta:
        name = "model"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"


@dataclass(kw_only=True)
class Abstractor(AbstractorType):
    """
    This is the root element for abstractors.
    """

    class Meta:
        name = "abstractor"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"


@dataclass(kw_only=True)
class MemoryMapType:
    """
    Map of address space blocks on slave slave bus interface.

    :ivar name: Unique name
    :ivar display_name:
    :ivar description:
    :ivar is_present:
    :ivar address_block:
    :ivar bank:
    :ivar subspace_map: Maps in an address subspace from across a bus
        bridge.  Its masterRef attribute refers by name to the master
        bus interface on the other side of the bridge.  It must match
        the masterRef attribute of a bridge element on the slave
        interface, and that bridge element must be designated as opaque.
    :ivar memory_remap: Additional memory map elements that are
        dependent on the component state.
    :ivar address_unit_bits:
    :ivar shared: When the value is 'yes', the contents of the memoryMap
        are shared by all the references to this memoryMap, when the
        value is 'no' the contents of the memoryMap is not shared and
        when the value is 'undefined' (default) the sharing of the
        memoryMap is undefined.
    :ivar vendor_extensions:
    :ivar id:
    """

    class Meta:
        name = "memoryMapType"

    name: str = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    display_name: None | DisplayName = field(
        default=None,
        metadata={
            "name": "displayName",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    is_present: None | IsPresent = field(
        default=None,
        metadata={
            "name": "isPresent",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    address_block: list[AddressBlock] = field(
        default_factory=list,
        metadata={
            "name": "addressBlock",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    bank: list[Bank] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    subspace_map: list[SubspaceRefType] = field(
        default_factory=list,
        metadata={
            "name": "subspaceMap",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    memory_remap: list[MemoryRemapType] = field(
        default_factory=list,
        metadata={
            "name": "memoryRemap",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    address_unit_bits: None | AddressUnitBits = field(
        default=None,
        metadata={
            "name": "addressUnitBits",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    shared: None | SharedType = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )


@dataclass(kw_only=True)
class MemoryMaps:
    """
    Lists all the slave memory maps defined by the component.

    :ivar memory_map: The set of address blocks a bus slave contributes
        to the bus' address space.
    """

    class Meta:
        name = "memoryMaps"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"

    memory_map: list[MemoryMapType] = field(
        default_factory=list,
        metadata={
            "name": "memoryMap",
            "type": "Element",
            "min_occurs": 1,
        },
    )


@dataclass(kw_only=True)
class ComponentType:
    """
    Component-specific extension to componentType.

    :ivar vendor: Name of the vendor who supplies this file.
    :ivar library: Name of the logical library this element belongs to.
    :ivar name: The name of the object.
    :ivar version: Indicates the version of the named element.
    :ivar bus_interfaces:
    :ivar indirect_interfaces:
    :ivar channels:
    :ivar remap_states:
    :ivar address_spaces:
    :ivar memory_maps:
    :ivar model:
    :ivar component_generators: Generator list is tools-specific.
    :ivar choices:
    :ivar file_sets:
    :ivar whitebox_elements: A list of whiteboxElements
    :ivar cpus: cpu's in the component
    :ivar other_clock_drivers: Defines a set of clock drivers that are
        not directly associated with an input port of the component.
    :ivar reset_types: A list of user defined resetTypes applicable to
        this component.
    :ivar description:
    :ivar parameters:
    :ivar assertions:
    :ivar vendor_extensions:
    :ivar id:
    """

    class Meta:
        name = "componentType"

    vendor: str = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    library: str = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    name: str = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    version: str = field(
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        }
    )
    bus_interfaces: None | BusInterfaces = field(
        default=None,
        metadata={
            "name": "busInterfaces",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    indirect_interfaces: None | IndirectInterfaces = field(
        default=None,
        metadata={
            "name": "indirectInterfaces",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    channels: None | Channels = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    remap_states: None | RemapStates = field(
        default=None,
        metadata={
            "name": "remapStates",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    address_spaces: None | AddressSpaces = field(
        default=None,
        metadata={
            "name": "addressSpaces",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    memory_maps: None | MemoryMaps = field(
        default=None,
        metadata={
            "name": "memoryMaps",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    model: None | Model = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    component_generators: None | ComponentGenerators = field(
        default=None,
        metadata={
            "name": "componentGenerators",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    choices: None | Choices = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    file_sets: None | FileSets = field(
        default=None,
        metadata={
            "name": "fileSets",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    whitebox_elements: None | ComponentType.WhiteboxElements = field(
        default=None,
        metadata={
            "name": "whiteboxElements",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    cpus: None | ComponentType.Cpus = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    other_clock_drivers: None | OtherClocks = field(
        default=None,
        metadata={
            "name": "otherClockDrivers",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    reset_types: None | ComponentType.ResetTypes = field(
        default=None,
        metadata={
            "name": "resetTypes",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    description: None | Description = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    parameters: None | Parameters = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    assertions: None | Assertions = field(
        default=None,
        metadata={
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    vendor_extensions: None | VendorExtensions = field(
        default=None,
        metadata={
            "name": "vendorExtensions",
            "type": "Element",
            "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
        },
    )
    id: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )

    @dataclass(kw_only=True)
    class WhiteboxElements:
        """
        :ivar whitebox_element: A whiteboxElement is a useful way to
            identify elements of a component that can not be identified
            through other means such as internal signals and non-
            software accessible registers.
        """

        whitebox_element: list[WhiteboxElementType] = field(
            default_factory=list,
            metadata={
                "name": "whiteboxElement",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                "min_occurs": 1,
            },
        )

    @dataclass(kw_only=True)
    class Cpus:
        """
        :ivar cpu: Describes a processor in this component.
        """

        cpu: list[ComponentType.Cpus.Cpu] = field(
            default_factory=list,
            metadata={
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                "min_occurs": 1,
            },
        )

        @dataclass(kw_only=True)
        class Cpu:
            """
            :ivar name: Unique name
            :ivar display_name:
            :ivar description:
            :ivar is_present:
            :ivar address_space_ref: Indicates which address space maps
                into this cpu.
            :ivar parameters: Data specific to the cpu.
            :ivar vendor_extensions:
            :ivar id:
            """

            name: str = field(
                metadata={
                    "type": "Element",
                    "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                }
            )
            display_name: None | DisplayName = field(
                default=None,
                metadata={
                    "name": "displayName",
                    "type": "Element",
                    "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                },
            )
            description: None | Description = field(
                default=None,
                metadata={
                    "type": "Element",
                    "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                },
            )
            is_present: None | IsPresent = field(
                default=None,
                metadata={
                    "name": "isPresent",
                    "type": "Element",
                    "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                },
            )
            address_space_ref: list[AddressSpaceRef] = field(
                default_factory=list,
                metadata={
                    "name": "addressSpaceRef",
                    "type": "Element",
                    "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                    "min_occurs": 1,
                },
            )
            parameters: None | Parameters = field(
                default=None,
                metadata={
                    "type": "Element",
                    "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                },
            )
            vendor_extensions: None | VendorExtensions = field(
                default=None,
                metadata={
                    "name": "vendorExtensions",
                    "type": "Element",
                    "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                },
            )
            id: None | str = field(
                default=None,
                metadata={
                    "type": "Attribute",
                    "namespace": "http://www.w3.org/XML/1998/namespace",
                },
            )

    @dataclass(kw_only=True)
    class ResetTypes:
        """
        :ivar reset_type: A user defined reset policy
        """

        reset_type: list[ComponentType.ResetTypes.ResetType] = field(
            default_factory=list,
            metadata={
                "name": "resetType",
                "type": "Element",
                "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                "min_occurs": 1,
            },
        )

        @dataclass(kw_only=True)
        class ResetType:
            """
            :ivar name: Unique name
            :ivar display_name:
            :ivar description:
            :ivar vendor_extensions:
            :ivar id:
            """

            name: str = field(
                metadata={
                    "type": "Element",
                    "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                }
            )
            display_name: None | DisplayName = field(
                default=None,
                metadata={
                    "name": "displayName",
                    "type": "Element",
                    "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                },
            )
            description: None | Description = field(
                default=None,
                metadata={
                    "type": "Element",
                    "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                },
            )
            vendor_extensions: None | VendorExtensions = field(
                default=None,
                metadata={
                    "name": "vendorExtensions",
                    "type": "Element",
                    "namespace": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
                },
            )
            id: None | str = field(
                default=None,
                metadata={
                    "type": "Attribute",
                    "namespace": "http://www.w3.org/XML/1998/namespace",
                },
            )


@dataclass(kw_only=True)
class Component(ComponentType):
    """
    This is the root element for all non platform-core components.
    """

    class Meta:
        name = "component"
        namespace = "http://www.accellera.org/XMLSchema/IPXACT/1685-2014"
