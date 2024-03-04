import {gql, useQuery} from '@apollo/client';

import {
  InstanceRunQueueConfigQuery,
  InstanceRunQueueConfigQueryVariables,
} from './types/useRunQueueConfig.types';

export const useRunQueueConfig = () => {
  const {data} = useQuery<InstanceRunQueueConfigQuery, InstanceRunQueueConfigQueryVariables>(
    INSTANCE_RUN_QUEUE_CONFIG,
  );
  return data?.instance.runQueueConfig;
};

const INSTANCE_RUN_QUEUE_CONFIG = gql`
  query InstanceRunQueueConfig {
    instance {
      id
      hasInfo
      runQueueConfig {
        maxConcurrentRuns
        tagConcurrencyLimitsYaml
        isOpConcurrencyAware
      }
    }
  }
`;
