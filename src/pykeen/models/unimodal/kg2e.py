# -*- coding: utf-8 -*-

"""Implementation of KG2E."""

import math
from typing import Optional

import torch
import torch.autograd

from ..base import TwoVectorEmbeddingModel
from ...losses import Loss
from ...nn.emb import EmbeddingSpecification
from ...nn.modules import KG2EInteraction
from ...regularizers import Regularizer
from ...triples import TriplesFactory
from ...typing import DeviceHint
from ...utils import clamp_norm

__all__ = [
    'KG2E',
]

_LOG_2_PI = math.log(2. * math.pi)


class KG2E(TwoVectorEmbeddingModel):
    r"""An implementation of KG2E from [he2015]_.

    KG2E aims to explicitly model (un)certainties in entities and relations (e.g. influenced by the number of triples
    observed for these entities and relations). Therefore, entities and relations are represented by probability
    distributions, in particular by multi-variate Gaussian distributions $\mathcal{N}_i(\mu_i,\Sigma_i)$
    where the mean $\mu_i \in \mathbb{R}^d$ denotes the position in the vector space and the diagonal variance
    $\Sigma_i \in \mathbb{R}^{d \times d}$ models the uncertainty.
    Inspired by the :class:`pykeen.models.TransE` model, relations are modeled as transformations from head to tail
    entities: $\mathcal{H} - \mathcal{T} \approx \mathcal{R}$ where
    $\mathcal{H} \sim \mathcal{N}_h(\mu_h,\Sigma_h)$, $\mathcal{H} \sim \mathcal{N}_t(\mu_t,\Sigma_t)$,
    $\mathcal{R} \sim \mathcal{P}_r = \mathcal{N}_r(\mu_r,\Sigma_r)$, and
    $\mathcal{H} - \mathcal{T} \sim \mathcal{P}_e = \mathcal{N}_{h-t}(\mu_h - \mu_t,\Sigma_h + \Sigma_t)$
    (since head and tail entities are considered to be independent with regards to the relations).
    The interaction model measures the similarity between $\mathcal{P}_e$ and $\mathcal{P}_r$ by
    means of the Kullback-Liebler Divergence (:meth:`KG2E.kullback_leibler_similarity`).

    .. math::
            f(h,r,t) = \mathcal{D_{KL}}(\mathcal{P}_e, \mathcal{P}_r)

    Besides the asymmetric KL divergence, the authors propose a symmetric variant which uses the expected
    likelihood (:meth:`KG2E.expected_likelihood`)

    .. math::
            f(h,r,t) = \mathcal{D_{EL}}(\mathcal{P}_e, \mathcal{P}_r)
    """

    #: The default strategy for optimizing the model's hyper-parameters
    hpo_default = dict(
        embedding_dim=dict(type=int, low=50, high=350, q=25),
        c_min=dict(type=float, low=0.01, high=0.1, scale='log'),
        c_max=dict(type=float, low=1.0, high=10.0),
    )

    def __init__(
        self,
        triples_factory: TriplesFactory,
        embedding_dim: int = 50,
        automatic_memory_optimization: Optional[bool] = None,
        loss: Optional[Loss] = None,
        preferred_device: DeviceHint = None,
        random_seed: Optional[int] = None,
        dist_similarity: Optional[str] = None,
        c_min: float = 0.05,
        c_max: float = 5.,
        regularizer: Optional[Regularizer] = None,
    ) -> None:
        r"""Initialize KG2E.

        :param embedding_dim: The entity embedding dimension $d$. Is usually $d \in [50, 350]$.
        :param dist_similarity: Either 'KL' for kullback-liebler or 'EL' for expected liklihood. Defaults to KL.
        :param c_min:
        :param c_max:
        """
        super().__init__(
            triples_factory=triples_factory,
            interaction_function=KG2EInteraction(
                similarity=dist_similarity,
            ),
            embedding_dim=embedding_dim,
            automatic_memory_optimization=automatic_memory_optimization,
            loss=loss,
            preferred_device=preferred_device,
            random_seed=random_seed,
            regularizer=regularizer,
            embedding_specification=EmbeddingSpecification(
                constrainer=clamp_norm,  # type: ignore
                constrainer_kwargs=dict(maxnorm=1., p=2, dim=-1),
            ),
            relation_embedding_specification=EmbeddingSpecification(
                constrainer=clamp_norm,  # type: ignore
                constrainer_kwargs=dict(maxnorm=1., p=2, dim=-1),
            ),
            # Ensure positive definite covariances matrices and appropriate size by clamping
            second_embedding_specification=EmbeddingSpecification(
                constrainer=torch.clamp,
                constrainer_kwargs=dict(min=c_min, max=c_max),
            ),
            second_relation_embedding_specification=EmbeddingSpecification(
                # Ensure positive definite covariances matrices and appropriate size by clamping
                constrainer=torch.clamp,
                constrainer_kwargs=dict(min=c_min, max=c_max),
            ),
        )
