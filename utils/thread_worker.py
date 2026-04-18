from PyQt6.QtCore import QThread, pyqtSignal
from core.pipeline import GauntletPipeline


class PipelineWorker(QThread):
    """
    Runs GauntletPipeline off the main thread so the UI never blocks.

    Signals:
        step_started(name, index)   -- before each agent
        pipeline_complete(result)   -- full result dict on success
        pipeline_error(message)     -- error string on exception
    """
    step_started      = pyqtSignal(str, int)
    pipeline_complete = pyqtSignal(dict)
    pipeline_error    = pyqtSignal(str)

    def __init__(self, agent_spec: str, domain: str, parent=None):
        super().__init__(parent)
        self.agent_spec = agent_spec
        self.domain     = domain

    def run(self):
        try:
            pipeline = GauntletPipeline(
                on_step=lambda name, idx: self.step_started.emit(name, idx)
            )
            result = pipeline.run(
                agent_spec=self.agent_spec,
                domain=self.domain,
            )
            self.pipeline_complete.emit(result)
        except Exception as e:
            self.pipeline_error.emit(str(e))
