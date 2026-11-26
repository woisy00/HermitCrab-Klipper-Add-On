# ~/klipper/klippy/extras/probe_offset_runtime.py
class ProbeOffsetRuntime:
    def __init__(self, config):
        self.printer = config.get_printer()
        gcode = self.printer.lookup_object('gcode')
        gcode.register_command('SET_PROBE_OFFSET', self.cmd_SET_PROBE_OFFSET,
                               desc="Set probe X/Y/Z offset at runtime "
                                    "(re-home Z after changing Z)")

    def cmd_SET_PROBE_OFFSET(self, gcmd):
        try:
            self._set_offsets(gcmd)
        except Exception as e:
            import logging, traceback
            logging.exception("SET_PROBE_OFFSET failed")
            raise gcmd.error("SET_PROBE_OFFSET failed: %s: %s"
                             % (type(e).__name__, e))
            
    def _set_offsets(self, gcmd):
        probe = self.printer.lookup_object('probe')
        po = probe.probe_offsets
        x = gcmd.get_float('X', po.x_offset)
        y = gcmd.get_float('Y', po.y_offset)
        z = gcmd.get_float('Z', po.z_offset)

        # X/Y/Z used for probing, PROBE_CALIBRATE, Z_OFFSET_APPLY_PROBE
        po.x_offset, po.y_offset, po.z_offset = x, y, z

        # Z also lives in the endstop wrapper and the Z rail (see above)
        if 'Z' in gcmd.get_command_parameters():
            wrapper = getattr(probe, 'mcu_probe', None)
            if wrapper is not None and hasattr(wrapper, 'position_endstop'):
                wrapper.position_endstop = z
            # kin = self.printer.lookup_object('toolhead').get_kinematics()
            # rail = kin.rails[2]
            # rail.position_endstop = z
            # rail.homing_info = rail.homing_info._replace(position_endstop=z)
            
            kin = self.printer.lookup_object('toolhead').get_kinematics()
            rail = kin.rails[2]
            rail.position_endstop = z
            # older versions cache the tuple, newer ones build it on demand
            if hasattr(rail, 'homing_info'):
                rail.homing_info = rail.homing_info._replace(
                    position_endstop=z)

        msg = "Probe offsets: X=%.3f Y=%.3f Z=%.3f" % (x, y, z)
        if 'Z' in gcmd.get_command_parameters():
            msg += " - run G28 Z now"
        gcmd.respond_info(msg)

def load_config(config):
    return ProbeOffsetRuntime(config)
