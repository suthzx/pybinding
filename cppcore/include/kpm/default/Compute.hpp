#pragma once
#include "kpm/Core.hpp"

namespace cpb { namespace kpm {

/**
 Default CPU implementation for computing KPM moments, see `Core`
 */
class DefaultCompute : public Compute::Interface {
public:
    void moments(MomentsRef m, Starter const& s, AlgorithmConfig const& ac,
                 OptimizedHamiltonian const& oh) const override;
};

}} // namespace cpb::kpm