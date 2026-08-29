<%namespace file="/license_header.mako" import="license"/>\
/*
${license(prefix=" *")}\
 */
/*
 * =============================================================================
 * OLLIVANDER AUTO-GENERATED OFFLOAD PAYLOAD LINKER SCRIPT
 * =============================================================================
 * Links the offload payload as one contiguous image at the payload region the
 * generator resolved: by default the second quarter of the boot memory (above
 * the host image and stack, inside the image's own dyn_mem VIEW - see the
 * payload-region comment in rtl_generator.py), or the window of the component
 * an explicit 'test_app.payload_memory' names, when the carve would not be
 * fetchable by the targets (the mesh case: narrow-only boot SPM against a
 * wide-refilling instruction cache). Every offload target fetches this same
 * single image; each run of it is confined to core-local state, so concurrent
 * readers are fine and the region is only ever written by the host's load.
 *
 * The image must stay contiguous and self-contained: bin2header.py embeds the
 * flat 'objcopy -O binary' output, whose bytes span from the region base to the
 * last loadable section - any gap or runtime-initialized section would either
 * bloat the embedded array or silently lose data (the payload keeps no .data or
 * .bss for exactly this reason, see payload_main.c).
 * =============================================================================
 */

OUTPUT_ARCH("riscv")
ENTRY(_start)

MEMORY
{
    /* Payload region resolved by the generator (rtl_generator.py) */
    payload (rx) : ORIGIN = ${hex(offload_payload_base)}, LENGTH = ${hex(offload_payload_size)}
}

SECTIONS
{
    /* Entry code first: the per-core boot addresses point at ORIGIN. */
    .text : {
        *(.text.init)
        *(.text*)
    } > payload

    .rodata : {
        *(.rodata*)
        *(.srodata*)
    } > payload

    /* Writable sections are forbidden by design - trap them at link time. */
    .data : { *(.data*) *(.sdata*) } > payload
    .bss  : { *(.bss*)  *(.sbss*) *(COMMON) } > payload
    ASSERT(SIZEOF(.data) == 0, "offload payload must not carry a .data section")
    ASSERT(SIZEOF(.bss)  == 0, "offload payload must not carry a .bss section")
}
