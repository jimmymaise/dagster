import {MockedProvider} from '@apollo/client/testing';
import * as React from 'react';

import {RunStatus} from '../../../graphql/types';
import {AutomaterializeMiddlePanelNoPartitions} from '../AutomaterializeMiddlePanelNoPartitions';
import {
  Evaluations,
  SINGLE_MATERIALIZE_RECORD_NO_PARTITIONS,
} from '../__fixtures__/AutoMaterializePolicyPage.fixtures';
import {buildRunStatusOnlyQuery} from '../__fixtures__/RunStatusOnlyQuery.fixtures';

// eslint-disable-next-line import/no-default-export
export default {component: AutomaterializeMiddlePanelNoPartitions};

const path = ['test'];

export const WithoutPartitions = () => {
  return (
    <MockedProvider
      mocks={[Evaluations.Single(path), buildRunStatusOnlyQuery('abcdef12', RunStatus.STARTED)]}
    >
      <div style={{width: '800px'}}>
        <AutomaterializeMiddlePanelNoPartitions
          selectedEvaluation={SINGLE_MATERIALIZE_RECORD_NO_PARTITIONS}
        />
      </div>
    </MockedProvider>
  );
};