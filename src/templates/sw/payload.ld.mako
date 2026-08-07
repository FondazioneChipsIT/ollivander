/*
 * =============================================================================
 * OLLIVANDER AUTO-GENERATED OFFLOAD PAYLOAD LINKER SCRIPT
 * =============================================================================
 * Links the offload payload as one contiguous image starting at the payload
 * region the generator carved out of the boot memory: its second quarter,
 * above the host image and stack (which the offload firmware caps at the
 * payload base) and deliberately inside the same lower-half VIEW of the
 * memory the image lives in - see the payload-region comment in
 * rtl_generator.py for the dyn_mem aliasing this avoids. Every offload
 * target reuses this same region: the offload test is sequential and
 * blocking, so at most one payload lives there at any time.
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
    /* Upper half of '${config.get("software_stack", {}).get("boot_memory", "")}' */
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
