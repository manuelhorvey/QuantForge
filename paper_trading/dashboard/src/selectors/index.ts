import {
  selectGovernance,
  selectGovernanceByAsset,
  selectGovernanceSummary,
} from './governance'

export {
  selectGovernance,
  selectGovernanceByAsset,
  selectGovernanceSummary,
}

export type { GovernanceState } from './governance'

export const selectors = {
  governance: {
    all: selectGovernance,
    byAsset: selectGovernanceByAsset,
    summary: selectGovernanceSummary,
  },
} as const
