from functools import partial

import colossalai
import pytest
import torch
import torch.multiprocessing as mp
from colossalai.amp.amp_type import AMP_TYPE
from colossalai.logging import get_dist_logger
from colossalai.trainer import Trainer
from colossalai.utils import MultiTimer, free_port
from tests.components_to_test.registry import non_distributed_component_funcs
from colossalai.testing import parameterize, rerun_on_exception

BATCH_SIZE = 4
IMG_SIZE = 32
NUM_EPOCHS = 200

CONFIG = dict(fp16=dict(mode=AMP_TYPE.TORCH))


@parameterize('model_name', ['repeated_computed_layers', 'resnet18', 'nested_model'])
def run_trainer(model_name):
    get_components_func = non_distributed_component_funcs.get_callable(model_name)
    model_builder, train_dataloader, test_dataloader, optimizer_class, criterion = get_components_func()
    model = model_builder()
    optimizer = optimizer_class(model.parameters(), lr=1e-3)
    engine, train_dataloader, *_ = colossalai.initialize(model=model,
                                                         optimizer=optimizer,
                                                         criterion=criterion,
                                                         train_dataloader=train_dataloader)

    logger = get_dist_logger()
    logger.info("engine is built", ranks=[0])

    timer = MultiTimer()
    trainer = Trainer(engine=engine, logger=logger, timer=timer)
    logger.info("trainer is built", ranks=[0])

    logger.info("start training", ranks=[0])
    trainer.fit(train_dataloader=train_dataloader,
                test_dataloader=test_dataloader,
                epochs=NUM_EPOCHS,
                max_steps=3,
                display_progress=True,
                test_interval=5)
    torch.cuda.empty_cache()


def run_dist(rank, world_size, port):
    colossalai.launch(config=CONFIG, rank=rank, world_size=world_size, host='localhost', port=port, backend='nccl')


@pytest.mark.dist
@rerun_on_exception(exception_type=mp.ProcessRaisedException, pattern=".*Address already in use.*")
def test_trainer_no_pipeline():
    world_size = 4
    run_func = partial(run_dist, world_size=world_size, port=free_port())
    mp.spawn(run_func, nprocs=world_size)


if __name__ == '__main__':
    test_trainer_no_pipeline()
