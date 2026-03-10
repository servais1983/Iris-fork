from iris_interface.IrisModuleInterface import IrisModuleInterface, IrisModuleTypes
import iris_interface.IrisInterfaceStatus as InterfaceStatus
import iris_mitre_module.IrisMitreConfig as interface_conf


class IrisMitreModule(IrisModuleInterface):
    """
    IrisMitre - exposes the MITRE ATT&CK matrix as an activatable module.
    Enabling this module makes the MITRE ATT&CK tab visible in case views.
    """
    _module_name = interface_conf.module_name
    _module_description = interface_conf.module_description
    _interface_version = interface_conf.interface_version
    _module_version = interface_conf.module_version
    _pipeline_support = interface_conf.pipeline_support
    _pipeline_info = interface_conf.pipeline_info
    _module_configuration = interface_conf.module_configuration
    _module_type = IrisModuleTypes.module_processor

    def register_hooks(self, module_id: int):
        """No hooks – this module only controls UI tab visibility."""
        pass

    def hooks_handler(self, hook_name: str, hook_ui_name: str, data: any):
        return InterfaceStatus.I2Success(data=data, logs=list(self.message_queue))
