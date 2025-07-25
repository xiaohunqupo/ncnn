# Copyright 2021 Tencent
# SPDX-License-Identifier: BSD-3-Clause

import torch
import torch.nn as nn
import torch.nn.functional as F

class Model(nn.Module):
    def __init__(self):
        super(Model, self).__init__()

        self.linear_0 = nn.Linear(in_features=64, out_features=16, bias=False)
        self.linear_1 = nn.Linear(in_features=16, out_features=3, bias=True)

    def forward(self, x, y, z, w):
        x = self.linear_0(x)
        x = self.linear_1(x)

        y = self.linear_0(y)
        y = self.linear_1(y)

        z = self.linear_0(z)
        z = self.linear_1(z)
        z = F.relu(z)

        w = self.linear_0(w)
        w = self.linear_1(w)
        return x, y, z, w

def test():
    net = Model().half().float()
    net.eval()

    torch.manual_seed(0)
    x = torch.rand(64)
    y = torch.rand(12, 64)
    z = torch.rand(1, 3, 12, 64)
    w = torch.rand(1, 64)

    a = net(x, y, z, w)

    # export torchscript
    mod = torch.jit.trace(net, (x, y, z, w))
    mod.save("test_nn_Linear.pt")

    # torchscript to pnnx
    import os
    os.system("../../src/pnnx test_nn_Linear.pt inputshape=[64],[12,64],[1,3,12,64],[1,64]")

    # ncnn inference
    import test_nn_Linear_ncnn
    b = test_nn_Linear_ncnn.test_inference()

    for a0, b0 in zip(a, b):
        if not torch.allclose(a0, b0, 1e-4, 1e-4):
            return False
    return True

if __name__ == "__main__":
    if test():
        exit(0)
    else:
        exit(1)
