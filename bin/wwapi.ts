#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { WwapiStack } from '../lib/wwapi-stack';
import { WwapiFrontendStack } from '../lib/wwapi-frontend-stack';

const app = new cdk.App();
const wwapistack = new WwapiStack(app, 'WwapiStack');
const wwapifrontendstack = new WwapiFrontendStack(app, 'WwapiFrontendStack' );

wwapifrontendstack.addDependency(wwapistack);